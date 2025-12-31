import { useEffect, useState } from "react";
import { fetchTestMetric } from "./api";

function App() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    fetchTestMetric().then(setData);
  }, []);

  return (
    <div>
      <h1>Health Aggregator</h1>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}

export default App;
