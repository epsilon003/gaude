const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

// Updated to match backend's list_collections_with_info() response
export interface RepoInfo {
  collection_name: string;
  source_url: string;
  commit_sha: string;
  chunk_count: number;
}

export interface Citation {
  file_path: string;
  start_line: number;
  end_line: number;
  rerank_score: number;
  text: string;
  github_url: string | null;
}

export interface ChatDoneEvent {
  event: "done";
  provider: string | null;
  model: string | null;
  confidence: number;
  confidence_label: string;
  resolved_question: string | null;
  retrieval_seconds: number;
  error: string | null;
  citations: Citation[];
}

export interface ChatTokenEvent {
  event: "token";
  text: string;
}

export type ChatEvent = ChatTokenEvent | ChatDoneEvent;

export interface IngestProgressEvent {
  event: "progress";
  message: string;
}

export interface IngestDoneEvent {
  event: "done";
  summary: { repo_url: string; collection_name: string; chunk_count: number };
}

export interface IngestErrorEvent {
  event: "error";
  message: string;
}

export type IngestEvent = IngestProgressEvent | IngestDoneEvent | IngestErrorEvent;

export interface HistoryTurn {
  question: string;
  answer: string;
}

/** 
 * Parses a `text/event-stream` response body into a stream of JSON-decoded
 * events. Shared by both ingestion progress and chat token streaming.
 */
async function* parseSSEStream<T>(response: Response): AsyncGenerator<T> {
  if (!response.body) {
    throw new Error("Response has no body to stream from.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? ""; // last (possibly incomplete) frame stays buffered
    for (const frame of frames) {
      const line = frame.trim();
      if (line.startsWith("data: ")) {
        yield JSON.parse(line.slice("data: ".length)) as T;
      }
    }
  }
}

export async function listRepos(): Promise<RepoInfo[]> {
  const res = await fetch(`${API_BASE}/api/repos`);
  if (!res.ok) {
    throw new Error(`Failed to list repos: ${res.status}`);
  }
  return res.json();
}

export async function* ingestRepoStream(repoUrl: string): AsyncGenerator<IngestEvent> {
  const startRes = await fetch(`${API_BASE}/api/repos/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ repo_url: repoUrl }),
  });
  if (!startRes.ok) {
    const detail = await startRes.text();
    throw new Error(`Failed to start ingestion: ${detail}`);
  }
  const { job_id: jobId } = (await startRes.json()) as { job_id: string };
  const eventsRes = await fetch(`${API_BASE}/api/repos/ingest/${jobId}/events`);
  if (!eventsRes.ok) {
    throw new Error(`Failed to subscribe to ingestion events: ${eventsRes.status}`);
  }
  yield* parseSSEStream<IngestEvent>(eventsRes);
}

export async function* chatStream(
  collection: string,
  question: string,
  history: HistoryTurn[],
  signal?: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ collection, question, history }),
    // Without this the caller's AbortController has nothing to abort: the
    // Stop button would flip the UI out of its streaming state while the
    // request kept running and tokens kept arriving in the background.
    signal,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to answer: ${detail}`);
  }
  yield* parseSSEStream<ChatEvent>(res);
}