import { useState, type FormEvent } from "react";
import { useToken } from "../auth/token";

export function TokenBar() {
  const { token, saveToken, clearToken } = useToken();
  const [draft, setDraft] = useState("");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (draft.trim() === "") {
      return;
    }
    saveToken(draft);
    setDraft("");
  }

  if (token !== "") {
    return (
      <div className="token-bar">
        <span className="muted">Token set for this tab</span>
        <button type="button" onClick={clearToken}>
          Forget token
        </button>
      </div>
    );
  }

  return (
    <form className="token-bar" onSubmit={submit}>
      <label htmlFor="api-token">API token</label>
      <input
        id="api-token"
        type="password"
        autoComplete="off"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
      />
      <button type="submit">Save</button>
    </form>
  );
}
