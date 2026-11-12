import type { Metadata } from "next";
import { NetworkWorkspace } from "@/components/network-workspace";

export const metadata: Metadata = { title: "Network intelligence" };

export default function NetworkPage() {
  return <NetworkWorkspace />;
}
