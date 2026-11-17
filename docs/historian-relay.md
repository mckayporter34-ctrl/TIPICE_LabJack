# Historian relay deployment

The repository's `Historian/Historian.py` now includes the deployed Pi's roster,
checkout, release, and heartbeat routes. It adds `GET /api/time` and
`POST /api/process-data`. It does not connect to hardware on import.

The tracked repository version retains its shared `core` configuration and
Python-version check. The private standalone deployment copy has those settings
embedded so it can run separately on the Pi.

## Deploy the Pi first

1. Keep a backup of the current deployed `historian.py` and its service command.
2. Copy the prepared standalone `Historian/private-deployment/historian.py` over
   the existing `~/historian.py` on the Pi.
   No repository checkout or `core` folder is required. Use the existing Python
   environment with Flask, influxdb-client, and labjack-ljm installed.
3. The private standalone copy already contains the original Pi database
   settings. Environment variables can override them. This directory is ignored
   by Git; never commit the populated token.
4. Set `HISTORIAN_STUDENTS_FILE` to the absolute path of the existing
   `students.txt`. If unset, the default is beside the deployed `historian.py`.
   Student rosters are ignored by Git.
5. Keep the existing service command when replacing the file in its original
   location. Preserve the existing user/network setup.
6. Restart the service when the equipment is idle: in-memory checkout sessions
   are cleared on restart. Check the service log for startup errors.
7. Verify `http://10.5.112.172:5000/api/time` returns a JSON `server_time_ns`.
   Confirm checkout, status, release, ESP32 readings, and idle machine polling.

The deployed calibration functions and channels are retained. `NNF` is renamed
to `NNF1` to match its IP and desktop configuration. Older database records keep
their old tags. Existing short STHX/CatMeth/PC names from the deployed source
are retained.

## Switch a managed desktop to relay mode

After the Pi is ready, merge these keys into that PC's ignored
`.historian.local.json` (preserve other existing keys):

```json
{
  "HISTORIAN_API_URL": "http://10.5.112.172:5000",
  "HISTORIAN_WRITE_MODE": "relay"
}
```

Environment variables with those names take precedence. Restart the desktop,
check out the apparatus with a roster ID, and start a short logging run. The
database upload count should increase and the new UUID-suffixed run should
appear in Grafana. Relay desktops do not require an InfluxDB token. Their
checkout/release/status requests now use the configured API URL too.

Direct database writing remains the default for staged rollout. Development
apparatuses bypass checkout and continue to use direct mode; they still need
their existing database settings. No automatic fallback from relay to direct
is allowed when a session is rejected. To roll back transport on a managed
desktop, explicitly set `HISTORIAN_WRITE_MODE` to `direct` and restore its
database credentials, then restart it.

## Timing, ownership, and delivery

The relay worker estimates the difference between PC and Pi clocks using a
request midpoint, then adjusts captured timestamps by that offset for the run.
It preserves sample spacing rather than assigning all queued samples their
arrival time. An offset above 30 seconds is shown in the upload indicator.
The estimate assumes the Pi clock is correct and approximately symmetric
network latency. Set both clocks to automatic time synchronization; changes
to a PC clock mid-run require stopping and restarting logging.

The Pi accepts only nonempty finite numeric field sets and validates the active
student owner for the specified unit before acknowledging a database write.
It uses the existing student-ID ownership model, not a new authentication
scheme. Upload requests do not renew the session; `/status` heartbeats do.
Ownership validation and database submission share a lock with takeover/release
so a queued request from a previous owner cannot pass after a takeover.

Database errors return HTTP 503; missing/expired/overridden ownership returns
403. Failed or dropped samples remain reported after later successes. They
are not retried automatically; retain the CSV for recovery. Uploads still
queued when checkout is released can be rejected; stop logging and let the
upload worker finish before disconnecting. A writer failure may be ambiguous
if the database accepted the point but its response was lost.

The endpoints preserve the existing LAN/HTTP deployment model. Enabling relay
does not disable existing direct database credentials on other machines.

## Validation

```sh
.venv/bin/python -m unittest discover -s tests -p test_data_logger.py
.venv/bin/python -m unittest discover -s tests -p test_historian_api.py
```

The API tests require Flask from `requirements.txt`. Hardware calls and database
writes are mocked; no test contacts lab equipment or the live historian.
