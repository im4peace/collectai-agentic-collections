import { RouterProvider } from "react-router-dom";

import { router } from "./app/router";

/** Root component (E3-S4 onward): mounts the router built in
 * `app/router.tsx`. Screens, layouts, guards and the persona switcher all
 * live under `app/` and `features/`, per `specs/design/folder-structure.md`. */
export function App(): JSX.Element {
  return <RouterProvider router={router} />;
}
