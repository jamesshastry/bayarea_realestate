import { redirect } from "next/navigation";

/**
 * Landing route — redirects to the Bay Area metro overview.
 *
 * Multi-metro expansion (F-MM-01) makes this configurable per `metro_id`
 * once Sacramento etc. land in Phase 5. For now, single-metro = redirect.
 */
export default function RootPage() {
  redirect("/bay-area");
}
