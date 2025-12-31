export async function fetchTestMetric() {
  const res = await fetch("/api/metrics/test");
  return res.json();
}
