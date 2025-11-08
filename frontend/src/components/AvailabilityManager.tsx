import { useEffect, useState } from "react";
import api from "../lib/api";

interface AvailabilityWindow {
  start: string;
  end: string;
}

interface AvailabilityManagerProps {
  companyId: string;
}

export function AvailabilityManager({ companyId }: AvailabilityManagerProps) {
  const [windows, setWindows] = useState<AvailabilityWindow[]>([
    { start: "", end: "" }
  ]);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      const response = await api.get(`/scheduler/${companyId}/availability`);
      setWindows(response.data.windows ?? [{ start: "", end: "" }]);
    };
    load();
  }, [companyId]);

  const updateWindow = (index: number, key: keyof AvailabilityWindow, value: string) => {
    setWindows((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], [key]: value };
      return copy;
    });
  };

  const addWindow = () => {
    setWindows((prev) => [...prev, { start: "", end: "" }]);
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    await api.post(`/scheduler/${companyId}/availability`, { windows });
    setMessage("Availability updated.");
  };

  return (
    <section className="panel">
      <header>
        <h2>Scheduling Availability</h2>
      </header>
      <form className="form-grid" onSubmit={save}>
        {windows.map((window, index) => (
          <div className="availability-row" key={index}>
            <label>
              Start
              <input
                type="datetime-local"
                value={window.start}
                onChange={(event) => updateWindow(index, "start", event.target.value)}
              />
            </label>
            <label>
              End
              <input
                type="datetime-local"
                value={window.end}
                onChange={(event) => updateWindow(index, "end", event.target.value)}
              />
            </label>
          </div>
        ))}
        <div className="actions-row">
          <button type="button" className="secondary" onClick={addWindow}>
            Add window
          </button>
          <button type="submit" className="primary">
            Save
          </button>
        </div>
      </form>
      {message && <p className="hint">{message}</p>}
    </section>
  );
}

