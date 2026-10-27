"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { forgetConcepts } from "@/lib/client/recent";

/** On a not-found concept page, take the concept off this browser's recent list. */
export function ForgetMissingConcept() {
  const pathname = usePathname();
  useEffect(() => {
    const match = /^\/concepts\/([^/]+)$/.exec(pathname);
    if (match) forgetConcepts([decodeURIComponent(match[1])]);
  }, [pathname]);
  return null;
}
