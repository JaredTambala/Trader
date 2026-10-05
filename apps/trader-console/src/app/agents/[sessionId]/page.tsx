import { AgentSessionWorkspace } from "../../../features/agent-sessions/agent-session-workspace";

export default async function AgentSessionPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  return <AgentSessionWorkspace sessionId={sessionId} />;
}
