import { useCallback, useMemo, useReducer } from "react";
import { FunctionalWorkspaceContext } from "./functionalWorkspaceContext.js";
import { EMPTY_FUNCTIONAL_WORKSPACE, functionalWorkspaceReducer } from "./functionalWorkspaceModel.js";

export default function FunctionalWorkspaceProvider({ children }) {
  const [state, dispatch] = useReducer(functionalWorkspaceReducer, EMPTY_FUNCTIONAL_WORKSPACE);
  const setWorkspace = useCallback((value) => dispatch({ type: "set", value }), []);
  const clearSelection = useCallback((message = "") => (
    dispatch({ type: "clear-selection", message })
  ), []);
  const leaveWorkspace = useCallback(() => dispatch({ type: "leave" }), []);
  const value = useMemo(() => ({ state, setWorkspace, clearSelection, leaveWorkspace }),
    [state, setWorkspace, clearSelection, leaveWorkspace]);
  return <FunctionalWorkspaceContext.Provider value={value}>{children}</FunctionalWorkspaceContext.Provider>;
}
