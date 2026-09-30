/**
 * ImdertyProfileCard — sección IMDERTY dentro del detalle de un atleta
 * (feature 047, US2). Orquesta:
 *  - `ImdertyProfileForm`: los campos no sensibles del perfil (apellidos,
 *    documento, dirección, barrio, institución, EPS, teléfono propio).
 *  - `PrimaryContactSelect`: cuál acudiente vinculado es el "contacto
 *    principal" (FR-022a).
 *  - `SensitiveDataCard`: etnia/discapacidad/víctima del conflicto, detrás
 *    de la autorización del acudiente — construido en paralelo
 *    (`src/components/imderty/SensitiveDataCard.tsx`), solo se importa acá.
 *
 * `GET /api/athletes/{id}/imderty-profile` nunca da 404: un perfil vacío
 * llega con nulls, así que el formulario siempre se puede pintar una vez
 * carga la query (contrato §Athlete IMDERTY profile).
 *
 * El filtro admin/coach vive en el punto de montaje (pestaña «Perfil
 * IMDERTY» de `routes/athletes/AthleteDetailPage.tsx`), no acá.
 */
import * as React from "react";
import { RefreshCw } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ImdertyProfileForm } from "@/components/imderty/ImdertyProfileForm";
import { PrimaryContactSelect } from "@/components/imderty/PrimaryContactSelect";
import { SensitiveDataCard } from "@/components/imderty/SensitiveDataCard";
import { IMDERTY_PROFILE_ANCHOR_ID } from "@/components/imderty/anchors";
import { useImdertyProfile } from "@/hooks/useImderty";

export interface ImdertyProfileCardProps {
  athleteId: number;
}

function ProfileSkeleton() {
  return (
    <div role="status" aria-busy="true" aria-label="Cargando perfil IMDERTY…" className="space-y-3">
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-12 w-full" />
    </div>
  );
}

export function ImdertyProfileCard({ athleteId }: ImdertyProfileCardProps) {
  const { data: profile, isLoading, isError, refetch } = useImdertyProfile(athleteId);
  const cardRef = React.useRef<HTMLDivElement>(null);
  const isReady = Boolean(profile) && !isLoading && !isError;

  // El navegador intenta saltar al ancla al cargar la ruta, pero en ese
  // momento la tarjeta aún no existe (la ficha y el perfil llegan por red).
  // Se desplaza una vez, cuando el perfil ya se pintó.
  React.useEffect(() => {
    if (!isReady) return;
    if (window.location.hash !== `#${IMDERTY_PROFILE_ANCHOR_ID}`) return;
    cardRef.current?.scrollIntoView?.({ block: "start" });
  }, [isReady]);

  return (
    <Card ref={cardRef} id={IMDERTY_PROFILE_ANCHOR_ID} className="scroll-mt-20">
      <CardHeader>
        <CardTitle>Perfil IMDERTY</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {isLoading && <ProfileSkeleton />}

        {isError && !isLoading && (
          <Alert variant="destructive">
            {/* Sin `AlertTitle` (h5) bajo el h3 de la tarjeta: regla axe heading-order. */}
            <AlertDescription className="space-y-2">
              <p>
                <strong>No se pudo cargar el perfil IMDERTY</strong>. Recarga la página o intenta
                de nuevo en un momento.
              </p>
              <Button type="button" variant="outline" size="sm" onClick={() => refetch()}>
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                Reintentar
              </Button>
            </AlertDescription>
          </Alert>
        )}

        {profile && !isLoading && !isError && (
          <>
            <ImdertyProfileForm athleteId={athleteId} profile={profile} />

            <div className="border-t border-hairline pt-5">
              <PrimaryContactSelect athleteId={athleteId} guardians={profile.guardians} />
            </div>

            <div className="border-t border-hairline pt-5">
              <SensitiveDataCard
                athleteId={athleteId}
                guardians={profile.guardians}
                authorization={profile.sensitive.authorization}
              />
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
