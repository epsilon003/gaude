const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface RepoInfo {
  name: string;
  source_url: string | null;
  display_name: string;
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
 * events. Shared by both ingestion progress and chat token streaming, since
 * the backend (api/main.py's `_sse()` helper) formats both identically:
 * `data: {...}\n\n` frames.
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

/**
 * Starts ingestion, then streams progress events until a `done` or `error`
 * event arrives. Two round-trips (start -> get job_id, then subscribe to its
 * event stream) mirroring the backend's two-endpoint design in api/main.py.
 */
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

/**
 * Streams a chat answer token-by-token, ending with one ChatDoneEvent
 * carrying citations/confidence/provider/timing.
 */
export async function* chatStream(
  collection: string,
  question: string,
  history: HistoryTurn[],
): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ collection, question, history }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Failed to answer: ${detail}`);
  }
  yield* parseSSEStream<ChatEvent>(res);
}
