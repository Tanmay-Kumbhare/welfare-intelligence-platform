import { Outlet } from "react-router-dom";
import AuthGate from "./AuthGate";

/**
 * Layout route for authenticated pages. The outer Layout already renders
 * Header/Footer, so this route only enforces authentication — otherwise the
 * header would render twice (once from Layout, once from here).
 */
export default function AuthLayout() {
  return (
    <AuthGate allowPublic={false}>
      <Outlet />
    </AuthGate>
  );
}
