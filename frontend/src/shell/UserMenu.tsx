import { LogOut, User } from "lucide-react";
import { useNavigate } from "react-router";
import type { Role } from "../api/types";
import { useSession } from "../auth/session";
import { Avatar } from "../ui/Avatar";
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
    <Menu
      label={me.username}
      trigger={
        <>
          <Avatar name={me.username} />
          <span className="hidden text-left leading-tight sm:grid">
            <span className="max-w-32 truncate">{me.username}</span>
            <span className="text-xs font-normal text-muted">{ROLE_LABELS[me.role]}</span>
          </span>
        </>
      }
      items={[
        { key: "account", label: "My account", icon: User, onSelect: () => navigate("/settings") },
        { key: "sign-out", label: "Sign out", icon: LogOut, danger: true, onSelect: logout },
      ]}
    />
  );
}
