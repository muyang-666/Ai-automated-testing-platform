import { useContext } from "react";
import { FunctionalWorkspaceContext } from "./functionalWorkspaceContext.js";

export default function useFunctionalWorkspace() {
  const value = useContext(FunctionalWorkspaceContext);
  if (!value) throw new Error("useFunctionalWorkspace must be used inside FunctionalWorkspaceProvider");
  return value;
}
