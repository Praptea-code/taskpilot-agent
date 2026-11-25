import { useCallback, useEffect, useRef, useState } from "react";

import "./styles.css";

type ScheduledAction = {
  id: number;
  local_time: string;
  duration_minutes: number;
  status: string;
};

type Notice = {
  id: number;
  title: string;
  body: string;
  level: string;
  created_at: string;
};

type VoiceReply = {
  text: string;
  audio_format: string;
};

type ChatMessage = {
  role: "user" | "agent";
  text: string;
};

function App() {
  const [apiKey, setApiKey] = useState("");
  const [goalText, setGoalText] = useState("");
  const [chatText, setChatText] = useState("");
  const [actions, setActions] = useState<ScheduledAction[]>([]);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [voiceReply, setVoiceReply] = useState<VoiceReply | null>(null);
  const [recording, setRecording] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const baseHeaders = useCallback(() => {
    const headers: Record<string, string> = { "X-User-Id": "1" };
    if (apiKey) {
      headers.Authorization = `Bearer ${apiKey}`;
    }
    return headers;
  }, [apiKey]);

  const jsonHeaders = useCallback(
    () => ({ ...baseHeaders(), "Content-Type": "application/json" }),
    [baseHeaders],
  );

  const loadNotices = useCallback(async () => {
    const response = await fetch("/notifications", { headers: baseHeaders() });
    if (response.ok) {
      setNotices((await response.json()) as Notice[]);
    }
  }, [baseHeaders]);

  useEffect(() => {
    void loadNotices();
  }, [loadNotices]);

  async function submitGoal(event: React.FormEvent) {
    event.preventDefault();
    if (!goalText.trim()) {
      return;
    }
    const created = await fetch("/goals", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({
        raw_input_text: goalText,
        domain: "general",
        auto_plan: false,
      }),
    });
    if (!created.ok) {
      throw new Error(await created.text());
    }
    const goal = (await created.json()) as { id: number };
    const planned = await fetch(`/goals/${goal.id}/plan`, {
      method: "POST",
      headers: jsonHeaders(),
    });
    if (!planned.ok) {
      throw new Error(await planned.text());
    }
    const plan = (await planned.json()) as {
      clarifying_question: string | null;
      schedule: { actions: ScheduledAction[] } | null;
    };
    setActions(plan.schedule?.actions ?? []);
    setMessages((current) => [
      ...current,
      {
        role: "agent",
        text: plan.clarifying_question ?? "Plan created and scheduled.",
      },
    ]);
    setGoalText("");
    await loadNotices();
  }

  async function sendChat(event: React.FormEvent) {
    event.preventDefault();
    if (!chatText.trim()) {
      return;
    }
    const text = chatText;
    setChatText("");
    setMessages((current) => [...current, { role: "user", text }]);
    const response = await fetch("/inbound", {
      method: "POST",
      headers: jsonHeaders(),
      body: JSON.stringify({ user_id: 1, text, channel: "chat" }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const result = (await response.json()) as { message: string };
    setMessages((current) => [...current, { role: "agent", text: result.message }]);
  }

  async function toggleRecording() {
    if (recording) {
      recorderRef.current?.stop();
      setRecording(false);
      return;
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    chunksRef.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        chunksRef.current.push(event.data);
      }
    };
    recorder.onstop = async () => {
      const blob = new Blob(chunksRef.current, {
        type: recorder.mimeType || "audio/webm",
      });
      const form = new FormData();
      form.append("audio", blob, "voice.webm");
      const response = await fetch("/voice", {
        method: "POST",
        headers: baseHeaders(),
        body: form,
      });
      if (response.ok) {
        const reply = (await response.json()) as VoiceReply;
        setVoiceReply(reply);
        setMessages((current) => [
          ...current,
          { role: "user", text: "Voice message" },
          { role: "agent", text: reply.text },
        ]);
      }
      stream.getTracks().forEach((track) => track.stop());
    };
    recorder.start();
    recorderRef.current = recorder;
    setRecording(true);
  }

  return (
    <main className="shell">
      <header>
        <h1>TaskPilot</h1>
        <label>
          API key
          <input
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="Optional for now"
          />
        </label>
      </header>

      <section className="grid">
        <div className="card">
          <h2>Goal</h2>
          <form onSubmit={submitGoal}>
            <textarea
              value={goalText}
              onChange={(event) => setGoalText(event.target.value)}
              placeholder="What do you want to get done?"
            />
            <button type="submit">Create plan</button>
          </form>
          <h3>Schedule</h3>
          <ul>
            {actions.map((action) => (
              <li key={action.id}>
                {action.local_time} for {action.duration_minutes} minutes, {action.status}
              </li>
            ))}
            {actions.length === 0 && <li>No scheduled actions yet.</li>}
          </ul>
        </div>

        <div className="card">
          <h2>Chat</h2>
          <div className="messages">
            {messages.map((message, index) => (
              <p key={`${message.role}-${index}`}>
                <strong>{message.role}:</strong> {message.text}
              </p>
            ))}
            {messages.length === 0 && <p>Ask a question or send a voice note.</p>}
          </div>
          <form onSubmit={sendChat}>
            <input
              value={chatText}
              onChange={(event) => setChatText(event.target.value)}
              placeholder="Type a message"
            />
            <button type="submit">Send</button>
          </form>
          <button type="button" onClick={() => void toggleRecording()}>
            {recording ? "Stop voice" : "Mic"}
          </button>
          {voiceReply && <p className="hint">Voice reply format: {voiceReply.audio_format}</p>}
        </div>

        <div className="card">
          <h2>Notifications</h2>
          <ul>
            {notices.map((notice) => (
              <li key={notice.id}>
                <strong>{notice.title}</strong> level {notice.level}: {notice.body}
              </li>
            ))}
            {notices.length === 0 && <li>No notifications yet.</li>}
          </ul>
          <button type="button" onClick={() => void loadNotices()}>
            Refresh
          </button>
        </div>
      </section>
    </main>
  );
}

export default App;
