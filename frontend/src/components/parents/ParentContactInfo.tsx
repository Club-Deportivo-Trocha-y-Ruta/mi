import { Mail, Phone, User } from "lucide-react";

import { cn } from "@/lib/utils";
import type { UserOut } from "@/types/user.types";

interface ParentContactInfoProps {
  parent: UserOut;
}

export function ParentContactInfo({ parent }: ParentContactInfoProps) {
  return (
    <div className={cn("rounded-xl bg-white p-5", "shadow-card")}>
      <h3
        className="font-display mb-4 flex items-center gap-2 text-sm text-charcoal"
        style={{ letterSpacing: "0.2px" }}
      >
        <User size={16} />
        Datos de contacto
      </h3>

      <dl className="space-y-3 text-sm">
        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-mid-gray">
            Nombre completo
          </dt>
          <dd className="mt-0.5 font-medium text-charcoal">
            {parent.first_name} {parent.last_name}
          </dd>
        </div>

        <div>
          <dt className="mb-0.5 text-xs font-medium uppercase tracking-wide text-mid-gray">
            Correo electrónico
          </dt>
          <dd className="flex items-center gap-1.5 font-medium text-charcoal">
            <Mail size={13} className="shrink-0 text-mid-gray" />
            {parent.email ?? (
              <span className="italic text-mid-gray">Sin correo registrado</span>
            )}
          </dd>
        </div>

        <div>
          <dt className="mb-0.5 text-xs font-medium uppercase tracking-wide text-mid-gray">
            Teléfono
          </dt>
          <dd className="flex items-center gap-1.5 font-medium text-charcoal">
            <Phone size={13} className="shrink-0 text-mid-gray" />
            {parent.phone ?? (
              <span className="italic text-mid-gray">Sin teléfono registrado</span>
            )}
          </dd>
        </div>

        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-mid-gray">
            Estado de cuenta
          </dt>
          <dd className="mt-0.5 flex items-center gap-1.5">
            <span
              className={cn(
                "inline-block h-2 w-2 rounded-full",
                parent.is_active ? "bg-green-500" : "bg-red-400",
              )}
            />
            <span className={cn("text-sm font-medium", parent.is_active ? "text-green-700" : "text-red-600")}>
              {parent.is_active ? "Activo" : "Inactivo"}
            </span>
          </dd>
        </div>
      </dl>
    </div>
  );
}
