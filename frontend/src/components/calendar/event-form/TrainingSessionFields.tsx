/**
 * TrainingSessionFields — placeholder informativo para event_type="training_session".
 *
 * Las sesiones de entrenamiento se gestionan en su propio módulo; el ID
 * se enlaza automáticamente al crear el evento de calendario.
 */
export function TrainingSessionFields() {
  return (
    <p className="text-sm text-mid-gray">
      Los entrenamientos en el calendario están vinculados al módulo de
      sesiones. El ID de sesión se enlazará automáticamente.
    </p>
  );
}
