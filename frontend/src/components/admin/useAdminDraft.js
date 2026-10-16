import { useRef, useState } from "react";

/**
 * Draft state for admin forms with dirty tracking + cancellation.
 *
 * - `fields` is the full field map (mounted with the current record values).
 * - `setField(name, value)` is the only mutator — keeps handlers one-liners.
 * - `dirty` compares live fields against the snapshot taken at mount, so
 *   forms never silently lose edits and callers can warn or disable.
 * - `reset()` restores that snapshot only on an explicit Cancel; nothing is
 *   discarded implicitly.
 */
export default function useAdminDraft(initialFields) {
  const [fields, setFields] = useState(() => ({ ...initialFields }));
  const initialRef = useRef({ ...initialFields });

  const setField = (name, value) =>
    setFields((current) => ({ ...current, [name]: value }));

  const dirty = Object.keys(fields).some(
    (key) => fields[key] !== initialRef.current[key]
  );

  const reset = () => setFields({ ...initialRef.current });

  return { fields, setField, dirty, reset };
}
