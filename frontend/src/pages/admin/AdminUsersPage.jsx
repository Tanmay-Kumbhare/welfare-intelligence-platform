import { useCallback, useEffect, useState } from "react";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import Input from "../../components/ui/Input";
import { ErrorState, LoadingState } from "../../components/ui/StatusStates";
import { extractApiErrorMessage } from "../../utils/apiError";
import { api } from "../../services/api";

export default function AdminUsersPage() {
  const [users, setUsers] = useState(null);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async (searchTerm) => {
    setError("");
    try {
      const response = await api.get("/admin/users", {
        params: searchTerm ? { search: searchTerm } : {},
      });
      setUsers(response.data);
    } catch (requestError) {
      setError(extractApiErrorMessage(requestError, "Could not load users."));
    }
  }, []);

  useEffect(() => {
    load("");
  }, [load]);

  const toggleAdmin = async (user) => {
    setBusyId(user.user_id);
    setMessage("");
    setError("");
    try {
      const hasAdmin = user.roles.includes("ADMIN");
      const nextRoles = hasAdmin
        ? user.roles.filter((r) => r !== "ADMIN")
        : [...user.roles, "ADMIN"];
      await api.patch(`/admin/users/${user.user_id}/roles`, { roles: nextRoles });
      setMessage(
        hasAdmin
          ? `ADMIN role removed from ${user.email}.`
          : `ADMIN role granted to ${user.email}.`
      );
      await load(search);
    } catch (requestError) {
      setError(extractApiErrorMessage(requestError, "Role update failed."));
    } finally {
      setBusyId(null);
    }
  };

  if (error && !users) {
    return <ErrorState title="Unable to load users" message={error} />;
  }
  if (!users) {
    return <LoadingState label="Loading users..." />;
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-[30px] mb-2">Users</h1>
        <p className="max-w-[60ch]">
          Accounts and their platform roles. Granting ADMIN gives full
          dashboard access on next sign-in.
        </p>
      </div>

      <div className="flex gap-3 mb-5 max-w-md">
        <Input
          id="admin-user-search"
          label="Search by email"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <div className="flex items-end mb-5">
          <Button variant="secondary" onClick={() => load(search)}>Search</Button>
        </div>
      </div>

      {message && (
        <div className="mb-4 text-[13px] text-ok-ink bg-ok-tint border border-ok-tint rounded-sm px-3 py-2">
          {message}
        </div>
      )}
      {error && (
        <div className="mb-4 text-[13px] text-excl-ink bg-excl-tint border border-excl-tint rounded-sm px-3 py-2">
          {error}
        </div>
      )}

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs text-ink-soft">
                <th className="py-2.5 pr-4">Email</th>
                <th className="py-2.5 pr-4">Roles</th>
                <th className="py-2.5 pr-4">Linked citizen</th>
                <th className="py-2.5 pr-4">Created</th>
                <th className="py-2.5">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {users.map((user) => (
                <tr key={user.user_id}>
                  <td className="py-2.5 pr-4 text-ink">{user.email}</td>
                  <td className="py-2.5 pr-4">
                    <div className="flex gap-1 flex-wrap">
                      {user.roles.length > 0 ? (
                        user.roles.map((role) => (
                          <span
                            key={role}
                            className={`text-xs px-2 py-0.5 rounded-sm ${
                              role === "ADMIN"
                                ? "bg-accent text-white"
                                : "bg-accent-tint text-accent-ink"
                            }`}
                          >
                            {role}
                          </span>
                        ))
                      ) : (
                        <span className="text-xs text-ink-soft">none</span>
                      )}
                    </div>
                  </td>
                  <td className="py-2.5 pr-4 text-xs text-ink-soft font-mono">
                    {user.citizen_id ? `${user.citizen_id.slice(0, 8)}…` : "—"}
                  </td>
                  <td className="py-2.5 pr-4 text-xs text-ink-soft">
                    {new Date(user.created_at).toLocaleDateString()}
                  </td>
                  <td className="py-2.5">
                    <Button
                      size="sm"
                      variant={user.roles.includes("ADMIN") ? "secondary" : "primary"}
                      disabled={busyId === user.user_id}
                      onClick={() => toggleAdmin(user)}
                    >
                      {user.roles.includes("ADMIN") ? "Revoke admin" : "Make admin"}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
