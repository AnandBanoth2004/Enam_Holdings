import type { Metadata } from "next";
import { CopilotWorkspace } from "@/components/copilot-workspace";

export const metadata: Metadata = { title: "Research copilot" };

export default function CopilotPage() {
  return <CopilotWorkspace />;
}
