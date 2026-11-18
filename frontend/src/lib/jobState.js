/** Keep the newer job when a slow or cached list arrives after a draft was filed. */
export function fresherJob(current, incoming) {
  if (!incoming) return current;
  if (!current) return incoming;
  const currentAt = current.updated_at || "";
  const incomingAt = incoming.updated_at || "";
  if (currentAt && incomingAt && incomingAt < currentAt) return current;
  return { ...current, ...incoming };
}

export function mergeJobList(current, incoming) {
  return (incoming || []).map(job => fresherJob(
    (current || []).find(item => item.id === job.id),
    job,
  ));
}
