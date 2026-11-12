import type { Metadata } from "next";
import { PushWorkspace } from "@/components/push-workspace";

export const metadata: Metadata = { title: "Push intelligence" };

export default function PushPage() {
  return <PushWorkspace />;
}
