import { Mail, Phone, User } from "lucide-react";

import { cn } from "@/lib/utils";
import type { UserOut } from "@/types/user.types";

const cardShadow =
  "rgba(19, 19, 22, 0.7) 0px 1px 5px -4px, rgba(34, 42, 53, 0.08) 0px 0px 0px 1px, rgba(34, 42, 53, 0.05) 0px 4px 8px 0px";

interface ParentContactInfoProps {
  parent: UserOut;
}

export function ParentContactInfo({ parent }: ParentContactInfoProps) {
  return (
    <div className="rounded-xl bg-white p-5" style={{ boxShadow: cardShadow }}>
      <h3
        className="mb-4 flex items-center gap-2 text-sm text-charcoal"
        style={{
          fontFamily: "'Cal Sans', system-ui, sans-serif",
          fontWeight: 600,
          letterSpacing: "0.2px",
        }}
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
