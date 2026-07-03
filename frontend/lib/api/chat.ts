import { apiClient, getApiBaseUrl, getStreamingHeaders } from "./client";
import type {
  ChatMessage,
  ChatResponse,
  Citation,
  ConfidenceMetadata,
  AgentStep,
  SuggestionsResponse,
  ConversationSuggestionsResponse,
  CursorPage,
  SendMessageRequest,
} from "./types";

export interface StreamCallbacks {
  onToken: (token: string) => void;
  onCitations?: (citations: Citation[]) => void;
  onConfidence?: (confidence: ConfidenceMetadata) => void;
  onAgentStep?: (step: AgentStep) => void;
  onComplete?: () => void;
  onError?: (error: Error) => void;
}

function parseStreamEvent(
  data: string,
  callbacks: StreamCallbacks
): "done" | "continue" {
  if (data === "[DONE]") return "done";

  if (!data.startsWith("{")) {
    try {
      callbacks.onToken(JSON.parse(data));
    } catch {
      callbacks.onToken(data);
    }
    return "continue";
  }

  try {
    const parsed = JSON.parse(data);

    if (parsed.type === "error") {
      throw new Error(parsed.error || "Stream error");
    }

    if (parsed.type === "agent_step" && parsed.step) {
      callbacks.onAgentStep?.(parsed.step as AgentStep);
      return "continue";
    }

    const citations = parsed.citations;
    const confidence = parsed.confidence;

    if (parsed.type === "metadata" || citations) {
      if (citations && callbacks.onCitations) {
        callbacks.onCitations(citations);
      }
      if (confidence && callbacks.onConfidence) {
        callbacks.onConfidence(confidence as ConfidenceMetadata);
      }
      return "continue";
    }

    callbacks.onToken(data);
  } catch (err) {
    if (err instanceof Error && err.message !== "Stream error") {
      callbacks.onToken(data);
    } else {
      throw err;
    }
  }

  return "continue";
}

export const chatApi = {
  /**
   * Get chat history for a notebook
   */
  getHistory: async (notebookId: string, limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) });
    const response = await apiClient<CursorPage<ChatMessage>>(`/chat/${notebookId}/history?${params}`);
    return response.items;
  },

  /**
   * Delete all chat messages for a notebook
   */
  deleteHistory: (notebookId: string) =>
    apiClient<void>(`/chat/${notebookId}/history`, { method: "DELETE" }),

  /**
   * Get AI-generated suggested questions based on notebook content
   */
  getSuggestions: (notebookId: string) =>
    apiClient<SuggestionsResponse>(`/chat/${notebookId}/suggestions`),

  /**
   * Get dynamic follow-up suggestions based on the last conversation turn
   */
  getConversationSuggestions: async (
    notebookId: string,
    lastUserMessage: string,
    lastAssistantMessage: string
  ): Promise<string[]> => {
    try {
      const response = await apiClient<ConversationSuggestionsResponse>(
        `/chat/${notebookId}/suggestions`,
        {
          method: "POST",
          body: JSON.stringify({
            last_user_message: lastUserMessage,
            last_assistant_message: lastAssistantMessage,
          }),
        }
      );
      return response.questions || [];
    } catch (error) {
      console.error("Failed to fetch conversation suggestions:", error);
      return [];
    }
  },

  /**
   * Send a message and get a non-streaming response
   */
  sendMessage: async (
    notebookId: string,
    message: string,
    options?: Pick<SendMessageRequest, "mode">
  ) => {
    const raw = await apiClient<Record<string, unknown>>(`/chat/${notebookId}/message`, {
      method: "POST",
      body: JSON.stringify({ message, stream: false, mode: options?.mode ?? "chat" }),
    });
    return {
      role: "assistant" as const,
      content: (raw.content as string) || (raw.message as string) || "",
      citations: (raw.citations as Citation[]) || [],
      confidence: raw.confidence as ConfidenceMetadata | undefined,
    };
  },

  /**
   * Send a message with streaming response (SSE)
   */
  sendMessageStream: async (
    notebookId: string,
    message: string,
    callbacks: StreamCallbacks,
    options?: Pick<SendMessageRequest, "mode"> & { signal?: AbortSignal }
  ) => {
    const { onComplete, onError, signal, ...streamCallbacks } = callbacks;
    const mode = options?.mode ?? "chat";

    try {
      const headers = await getStreamingHeaders();

      const response = await fetch(
        `${getApiBaseUrl()}/api/v1/chat/${notebookId}/message`,
        {
          method: "POST",
          headers,
          body: JSON.stringify({
            message,
            stream: true,
            mode,
          }),
          signal,
        }
      );

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Stream failed" }));
        throw new Error(error.detail || "Failed to send message");
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const result = parseStreamEvent(line.slice(6), streamCallbacks);
            if (result === "done") break;
          }
        }
      }

      onComplete?.();
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      if (onError) {
        onError(error instanceof Error ? error : new Error("Unknown streaming error"));
      } else {
        throw error;
      }
    }
  },
};
