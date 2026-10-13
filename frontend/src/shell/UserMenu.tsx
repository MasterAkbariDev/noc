import { LogOut, User } from "lucide-react";
import { useNavigate } from "react-router";
import type { Role } from "../api/types";
import { useSession } from "../auth/session";
import { Menu } from "../ui/Menu";

const ROLE_LABELS: Record<Role, string> = {
  viewer: "Viewer",
  operator: "Operator",
  admin: "Admin",
};

export function UserMenu() {
  const { me, logout } = useSession();
  const navigate = useNavigate();

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted">{ROLE_LABELS[me.role]}</span>
      <Menu
        label={me.username}
        items={[
          { key: "account", label: "My account", icon: User, onSelect: () => navigate("/settings") },
          { key: "sign-out", label: "Sign out", icon: LogOut, danger: true, onSelect: logout },
        ]}
      />
    </div>
  );
}
