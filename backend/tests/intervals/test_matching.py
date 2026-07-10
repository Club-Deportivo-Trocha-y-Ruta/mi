"""Tests unitarios para app.services.intervals.matching.compute_match.

Motor puro, determinístico, sin I/O (ver docstring del módulo y research.md
D5). Cubre:
  - Flattening de repeat-group (vía ``structures.flatten_blocks``) alimentado
    a ``compute_match`` — confirma que el motor empareja correctamente los
    pasos ya expandidos, en el orden real de ejecución.
  - Pairing posicional por orden (``plan[i] <-> lap[i]``), incluso cuando las
    vueltas llegan desordenadas por ``lap_index``.
  - Bordes exactos de la tolerancia ±30 %.
  - Descarte de vueltas de ruido (< 10 s) antes del emparejamiento.
  - Menos laps que bloques -> ``sin_dato``; más laps que bloques -> ``extra``;
    cero laps -> todos los bloques ``sin_dato``.
  - Shape y summary del ``result_json`` (``MatchResultPayload``).

No usa base de datos ni fixtures async — ``compute_match`` no las necesita.
"""

import pytest

from app.schemas.intervals import BlockIn, MatchResultPayload
from app.services.intervals.matching import (
    DURATION_TOLERANCE_FRACTION,
    MIN_LAP_ELAPSED_S,
    TOLERANCE_PCT,
    FlattenedBlock,
    MatchLap,
    compute_match,
)
from app.services.intervals.structures import flatten_blocks

# ---------------------------------------------------------------------------
# Flattening de repeat-group -> compute_match
# ---------------------------------------------------------------------------


class TestFlatteningRepeatGroupIntoMatching:
    """El motor consume pasos ya aplanados; estos tests verifican que un
    repeat-group real (aplanado con ``structures.flatten_blocks``) se
    empareja correctamente en el orden de ejecución, no en el orden de
    autoría."""

    def _repeat_group_blocks(self) -> list[BlockIn]:
        return [
            BlockIn(
                position=1, block_type="warmup", duration_s=300,
                target_zone="Z1", target_cadence_rpm=70,
            ),
            BlockIn(
                position=2, block_type="work", duration_s=120,
                target_zone="Z2", target_cadence_rpm=75,
                repeat_group=1, repeat_count=2,
            ),
            BlockIn(
                position=3, block_type="recovery", duration_s=60,
                target_zone="Z1", target_cadence_rpm=65,
                repeat_group=1, repeat_count=2,
            ),
            BlockIn(
                position=4, block_type="cooldown", duration_s=300,
                target_zone="Z1", target_cadence_rpm=65,
            ),
        ]

    def test_expands_to_six_steps_in_execution_order(self):
        flattened = flatten_blocks(self._repeat_group_blocks())

        assert [step.block_type for step in flattened] == [
            "warmup", "work", "recovery", "work", "recovery", "cooldown",
        ]
        assert [step.repeat_iteration for step in flattened] == [
            None, 1, 1, 2, 2, None,
        ]

    def test_matches_expanded_steps_positionally_against_laps(self):
        flattened = flatten_blocks(self._repeat_group_blocks())
        # Una vuelta por cada paso real (6), todas dentro de tolerancia.
        laps = [
            MatchLap(lap_index=i, elapsed_time_s=step.planned_duration_s)
            for i, step in enumerate(flattened)
        ]

        result = compute_match(flattened, laps)

        assert len(result.blocks) == 6
        assert [b.status for b in result.blocks] == ["cumplido"] * 6
        assert [b.repeat_iteration for b in result.blocks] == [
            None, 1, 1, 2, 2, None,
        ]
        # flat_index sigue el orden real de ejecución, no la posición de autoría.
        assert [b.flat_index for b in result.blocks] == list(range(6))
        assert result.summary.cumplido == 6
        assert result.summary.fuera_tolerancia == 0
        assert result.summary.sin_dato == 0
        assert result.summary.extra == 0


# ---------------------------------------------------------------------------
# Pairing por orden (plan[i] <-> lap[i])
# ---------------------------------------------------------------------------


class TestPairingByOrder:
    def test_pairs_positionally_regardless_of_input_list_order(self):
        blocks = [
            FlattenedBlock(
                block_type="warmup", planned_duration_s=300,
                target_zone="Z1", target_cadence_rpm=70,
            ),
            FlattenedBlock(
                block_type="work", planned_duration_s=120,
                target_zone="Z2", target_cadence_rpm=75,
            ),
        ]
        # Las vueltas llegan en orden inverso al de ``lap_index`` — el motor
        # debe reordenarlas por ``lap_index`` antes de emparejar (D5, paso 2).
        laps = [
            MatchLap(lap_index=1, elapsed_time_s=120),
            MatchLap(lap_index=0, elapsed_time_s=300),
        ]

        result = compute_match(blocks, laps)

        assert result.blocks[0].lap_index == 0
        assert result.blocks[0].lap_elapsed_time_s == 300
        assert result.blocks[0].status == "cumplido"
        assert result.blocks[1].lap_index == 1
        assert result.blocks[1].lap_elapsed_time_s == 120
        assert result.blocks[1].status == "cumplido"

    def test_block_and_lap_identity_fields_are_echoed(self):
        blocks = [
            FlattenedBlock(
                block_type="work", planned_duration_s=100, target_zone="Z3",
                target_cadence_rpm=80, block_id=42, repeat_iteration=3,
            ),
        ]
        laps = [MatchLap(lap_index=5, elapsed_time_s=100, average_heartrate=150.2)]

        result = compute_match(blocks, laps)

        block = result.blocks[0]
        assert block.block_id == 42
        assert block.repeat_iteration == 3
        assert block.block_type == "work"
        assert block.target_zone == "Z3"
        assert block.target_cadence_rpm == 80
        assert block.lap_index == 5
        assert block.lap_average_heartrate == 150.2


# ---------------------------------------------------------------------------
# Bordes de tolerancia ±30 %
# ---------------------------------------------------------------------------


class TestToleranceBoundaries:
    def test_tolerance_fraction_and_pct_constants_are_consistent(self):
        assert DURATION_TOLERANCE_FRACTION == 0.30
        assert TOLERANCE_PCT == 30

    @pytest.mark.parametrize(
        ("lap_elapsed_s", "expected_status"),
        [
            (390, "cumplido"),        # +30% exacto -> dentro de tolerancia
            (391, "fuera_tolerancia"),  # +30% + 1s -> excede
            (210, "cumplido"),        # -30% exacto -> dentro de tolerancia
            (209, "fuera_tolerancia"),  # -30% - 1s -> excede
            (300, "cumplido"),        # exacto, sin desviación
        ],
    )
    def test_boundary_values_around_300s_plan(self, lap_elapsed_s, expected_status):
        blocks = [
            FlattenedBlock(
                block_type="work", planned_duration_s=300,
                target_zone="Z2", target_cadence_rpm=75,
            ),
        ]
        laps = [MatchLap(lap_index=0, elapsed_time_s=lap_elapsed_s)]

        result = compute_match(blocks, laps)

        assert result.blocks[0].status == expected_status


# ---------------------------------------------------------------------------
# Descarte de vueltas de ruido (< 10 s)
# ---------------------------------------------------------------------------


class TestDiscardShortLaps:
    def test_min_lap_elapsed_constant(self):
        assert MIN_LAP_ELAPSED_S == 10

    def test_laps_under_10s_are_discarded_and_counted(self):
        blocks = [
            FlattenedBlock(
                block_type="warmup", planned_duration_s=300,
                target_zone="Z1", target_cadence_rpm=70,
            ),
            FlattenedBlock(
                block_type="work", planned_duration_s=120,
                target_zone="Z2", target_cadence_rpm=75,
            ),
        ]
        # Vueltas de ruido (< 10s) intercaladas entre las reales.
        laps = [
            MatchLap(lap_index=0, elapsed_time_s=5),    # ruido, descartada
            MatchLap(lap_index=1, elapsed_time_s=300),  # real -> bloque 0
            MatchLap(lap_index=2, elapsed_time_s=9),    # ruido, descartada
            MatchLap(lap_index=3, elapsed_time_s=120),  # real -> bloque 1
        ]

        result = compute_match(blocks, laps)

        assert result.laps_discarded_under_10s == 2
        assert result.blocks[0].lap_index == 1
        assert result.blocks[0].lap_elapsed_time_s == 300
        assert result.blocks[0].status == "cumplido"
        assert result.blocks[1].lap_index == 3
        assert result.blocks[1].lap_elapsed_time_s == 120
        assert result.blocks[1].status == "cumplido"

    def test_exactly_10s_lap_is_kept_not_discarded(self):
        blocks = [
            FlattenedBlock(
                block_type="work", planned_duration_s=10,
                target_zone="Z2", target_cadence_rpm=75,
            ),
        ]
        laps = [MatchLap(lap_index=0, elapsed_time_s=10)]

        result = compute_match(blocks, laps)

        assert result.laps_discarded_under_10s == 0
        assert result.blocks[0].lap_index == 0
        assert result.blocks[0].status == "cumplido"

    def test_all_laps_under_10s_yields_no_data_for_every_block(self):
        blocks = [
            FlattenedBlock(
                block_type="warmup", planned_duration_s=300,
                target_zone="Z1", target_cadence_rpm=70,
            ),
        ]
        laps = [
            MatchLap(lap_index=0, elapsed_time_s=2),
            MatchLap(lap_index=1, elapsed_time_s=7),
        ]

        result = compute_match(blocks, laps)

        assert result.laps_discarded_under_10s == 2
        assert result.blocks[0].status == "sin_dato"
        assert result.blocks[0].lap_index is None
        assert result.extra_laps == []


# ---------------------------------------------------------------------------
# Menos / más / cero laps -> sin_dato / extra
# ---------------------------------------------------------------------------


class TestLapCountMismatch:
    def _three_blocks(self) -> list[FlattenedBlock]:
        return [
            FlattenedBlock(
                block_type="warmup", planned_duration_s=300,
                target_zone="Z1", target_cadence_rpm=70,
            ),
            FlattenedBlock(
                block_type="work", planned_duration_s=120,
                target_zone="Z2", target_cadence_rpm=75,
            ),
            FlattenedBlock(
                block_type="cooldown", planned_duration_s=300,
                target_zone="Z1", target_cadence_rpm=65,
            ),
        ]

    def test_fewer_laps_than_blocks_yields_sin_dato_for_trailing_blocks(self):
        blocks = self._three_blocks()
        laps = [MatchLap(lap_index=0, elapsed_time_s=300)]  # solo 1 de 3

        result = compute_match(blocks, laps)

        assert result.blocks[0].status == "cumplido"
        assert result.blocks[1].status == "sin_dato"
        assert result.blocks[1].lap_index is None
        assert result.blocks[1].lap_elapsed_time_s is None
        assert result.blocks[1].lap_average_heartrate is None
        assert result.blocks[2].status == "sin_dato"
        assert result.summary.cumplido == 1
        assert result.summary.sin_dato == 2
        assert result.summary.extra == 0
        assert result.extra_laps == []

    def test_more_laps_than_blocks_yields_extra_rows_never_dropped(self):
        blocks = [
            FlattenedBlock(
                block_type="warmup", planned_duration_s=300,
                target_zone="Z1", target_cadence_rpm=70,
            ),
        ]
        laps = [
            MatchLap(lap_index=0, elapsed_time_s=300),
            MatchLap(lap_index=1, elapsed_time_s=45, average_heartrate=140.0),
            MatchLap(lap_index=2, elapsed_time_s=60),
        ]

        result = compute_match(blocks, laps)

        assert len(result.blocks) == 1
        assert result.blocks[0].status == "cumplido"
        assert len(result.extra_laps) == 2
        assert result.extra_laps[0].lap_index == 1
        assert result.extra_laps[0].elapsed_time_s == 45
        assert result.extra_laps[0].average_heartrate == 140.0
        assert result.extra_laps[1].lap_index == 2
        assert result.extra_laps[1].elapsed_time_s == 60
        assert result.summary.extra == 2

    def test_zero_laps_yields_sin_dato_for_every_block(self):
        blocks = self._three_blocks()

        result = compute_match(blocks, [])

        assert [b.status for b in result.blocks] == ["sin_dato"] * 3
        assert result.summary.sin_dato == 3
        assert result.summary.cumplido == 0
        assert result.summary.fuera_tolerancia == 0
        assert result.summary.extra == 0
        assert result.extra_laps == []
        assert result.laps_discarded_under_10s == 0

    def test_zero_blocks_with_laps_yields_all_extra(self):
        # Caso límite adicional: sin plan, todas las vueltas son informativas.
        laps = [
            MatchLap(lap_index=0, elapsed_time_s=300),
            MatchLap(lap_index=1, elapsed_time_s=120),
        ]

        result = compute_match([], laps)

        assert result.blocks == []
        assert len(result.extra_laps) == 2
        assert result.summary.extra == 2
        assert result.summary.cumplido == 0
        assert result.summary.sin_dato == 0


# ---------------------------------------------------------------------------
# Shape + summary del result_json (MatchResultPayload)
# ---------------------------------------------------------------------------


class TestResultPayloadShape:
    def _mixed_scenario(self):
        """3 bloques, 2 laps: cumplido + fuera_tolerancia + sin_dato.

        El emparejamiento es posicional (D5): con menos laps que bloques el
        bloque sobrante siempre es ``sin_dato`` y nunca hay filas ``extra`` en
        la misma corrida (son mutuamente excluyentes — ``extra`` solo aparece
        cuando sobran laps, ver ``_scenario_with_extra_lap``).
        """
        blocks = [
            FlattenedBlock(
                block_type="warmup", planned_duration_s=300,
                target_zone="Z1", target_cadence_rpm=70, block_id=1,
            ),
            FlattenedBlock(
                block_type="work", planned_duration_s=120,
                target_zone="Z3", target_cadence_rpm=80, block_id=2,
                repeat_iteration=1,
            ),
            FlattenedBlock(
                block_type="cooldown", planned_duration_s=300,
                target_zone="Z1", target_cadence_rpm=65, block_id=3,
            ),
        ]
        laps = [
            MatchLap(lap_index=0, elapsed_time_s=300, average_heartrate=125.0),  # cumplido
            MatchLap(lap_index=1, elapsed_time_s=200, average_heartrate=170.0),  # fuera_tolerancia
            # bloque 2 (cooldown) no tiene vuelta emparejada -> sin_dato
        ]
        return blocks, laps

    def _scenario_with_extra_lap(self):
        """1 bloque, 2 laps: la segunda vuelta sobra -> fila ``extra``."""
        blocks = [
            FlattenedBlock(
                block_type="warmup", planned_duration_s=300,
                target_zone="Z1", target_cadence_rpm=70, block_id=1,
            ),
        ]
        laps = [
            MatchLap(lap_index=0, elapsed_time_s=300, average_heartrate=125.0),
            MatchLap(lap_index=1, elapsed_time_s=45, average_heartrate=140.0),
        ]
        return blocks, laps

    def test_returns_a_match_result_payload_instance(self):
        blocks, laps = self._mixed_scenario()

        result = compute_match(blocks, laps)

        assert isinstance(result, MatchResultPayload)

    def test_top_level_shape_matches_data_model_contract(self):
        blocks, laps = self._mixed_scenario()

        result = compute_match(blocks, laps)
        dumped = result.model_dump()

        assert set(dumped.keys()) == {
            "blocks", "extra_laps", "summary", "tolerance_pct",
            "laps_discarded_under_10s",
        }
        assert dumped["tolerance_pct"] == 30

    def test_block_row_shape_matches_data_model_contract(self):
        blocks, laps = self._mixed_scenario()

        result = compute_match(blocks, laps)
        block_dict = result.blocks[0].model_dump()

        assert set(block_dict.keys()) == {
            "flat_index", "block_id", "block_type", "repeat_iteration",
            "planned_duration_s", "target_zone", "target_cadence_rpm",
            "lap_index", "lap_elapsed_time_s", "lap_average_heartrate",
            "status",
        }

    def test_extra_lap_row_shape_matches_data_model_contract(self):
        blocks, laps = self._scenario_with_extra_lap()

        result = compute_match(blocks, laps)
        extra_dict = result.extra_laps[0].model_dump()

        assert set(extra_dict.keys()) == {
            "lap_index", "elapsed_time_s", "average_heartrate",
        }
        assert result.summary.extra == 1

    def test_summary_counts_reconcile_with_block_statuses(self):
        blocks, laps = self._mixed_scenario()

        result = compute_match(blocks, laps)

        assert result.blocks[0].status == "cumplido"
        assert result.blocks[1].status == "fuera_tolerancia"
        assert result.blocks[2].status == "sin_dato"
        assert result.summary.cumplido == 1
        assert result.summary.fuera_tolerancia == 1
        assert result.summary.sin_dato == 1
        assert result.summary.extra == 0
        assert result.extra_laps == []
        # El total de bloques (no-extra) siempre coincide con len(blocks).
        assert (
            result.summary.cumplido
            + result.summary.fuera_tolerancia
            + result.summary.sin_dato
        ) == len(result.blocks)
        # Las vueltas extra nunca se cuentan contra bloques del plan.
        assert result.summary.extra == len(result.extra_laps)

    def test_engine_version_constant_is_stable(self):
        from app.services.intervals.matching import ENGINE_VERSION

        assert ENGINE_VERSION == 1
