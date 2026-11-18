/* Optional, read-only DevTools snippet. Aggregate counts only; no URLs, cookies,
 * identifiers, packet bodies or browser storage are exported. It does not install
 * an updater, intercept network traffic or cache any assets. Copy its JSON output
 * separately for a cold and a warm visit using the same browser profile. */
(() => {
  const groups = {};
  for (const entry of performance.getEntriesByType('resource')) {
    const group = groups[entry.initiatorType || 'other'] ||= {
      requests: 0, transfer_bytes: 0, encoded_body_bytes: 0,
      decoded_body_bytes: 0, zero_transfer_entries: 0
    };
    group.requests++;
    group.transfer_bytes += entry.transferSize || 0;
    group.encoded_body_bytes += entry.encodedBodySize || 0;
    group.decoded_body_bytes += entry.decodedBodySize || 0;
    if (entry.transferSize === 0) group.zero_transfer_entries++;
  }
  const navigation = performance.getEntriesByType('navigation')[0];
  const result = {
    schema_version: 1, elapsed_ms: Math.round(performance.now()), resources: groups,
    navigation: navigation ? {
      transfer_bytes: navigation.transferSize, encoded_body_bytes: navigation.encodedBodySize,
      decoded_body_bytes: navigation.decodedBodySize
    } : null,
    limitations: [
      'A snapshot covers only retained timing entries on this page; entries may have been evicted.',
      'WebSocket traffic is not counted here; use host/provider counters for that category.',
      'Zero transfer can mean caching OR unavailable timing information; it is not proof of a cache hit.',
      'Transfer size includes HTTP overhead but is not a complete TLS/network or billing measurement.'
    ]
  };
  console.log(JSON.stringify(result, null, 2));
  return result;
})();
