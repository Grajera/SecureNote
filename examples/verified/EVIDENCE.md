# Verified example evidence

These are measured local CPU runs with Python socket connections blocked.
Synthetic speech only. Full transcript, notes, logs and summaries are in each run folder.

## business

Run folder: `examples/verified/runs/20261023T005036-76e4817e`

Status: ok; elapsed: 1616.5 ms

Input: `examples/media/business.wav`; search: `budget deadline`

# SecureNote - automatic candidate notes

Review against the recording. Extractive baseline; speaker identity is unknown.
Timestamps identify containing ASR segments, not exact sentence boundaries.

## Decisions

- [00:00:02.74 - 00:00:07.04] We decided to use the local server for all meeting recordings.

## Action items

- [00:00:07.04 - 00:00:10.38] Alice will send the revised budget by Friday.

## Questions

- [00:00:14.20 - 00:00:16.88] Do we need a second backup drive?

## Key points

- [00:00:00.00 - 00:00:02.74] Today we reviewed the project schedule.
- [00:00:10.38 - 00:00:14.20] The main risk is limited storage on the recording device.
- [00:00:16.88 - 00:00:18.88] The next meeting is on Monday.

## Search results

### budget deadline

- [00:00:07.04] Alice will send the revised budget by Friday. (score 0.447)


```json
[
  {
    "stage": "validation",
    "event": "completed",
    "latency_ms": 51.94
  },
  {
    "stage": "model_inference",
    "event": "completed",
    "latency_ms": 1500.8
  },
  {
    "stage": "postprocessing",
    "event": "completed",
    "latency_ms": 1.25
  },
  {
    "stage": "retrieval",
    "event": "completed",
    "latency_ms": 0.18
  },
  {
    "stage": "run",
    "event": "finished",
    "latency_ms": 1616.5,
    "status": "ok"
  }
]
```

## lecture

Run folder: `examples/verified/runs/20261023T005037-3da8c5ab`

Status: ok; elapsed: 1758.35 ms

Input: `examples/media/lecture.mp3`; search: `discount factor homework`

# SecureNote - automatic candidate notes

Review against the recording. Extractive baseline; speaker identity is unknown.
Timestamps identify containing ASR segments, not exact sentence boundaries.

## Questions

- [00:00:13.04 - 00:00:24.40] How does exploration affect Thirding, the MMM will cover value iteration and policy iteration

## Key points

- [00:00:00.00 - 00:00:06.52] Today's lecture covers reinforcement learning.
- [00:00:00.00 - 00:00:06.52] A policy map sustained to an action.
- [00:00:00.00 - 00:00:13.04] A value function estimates expected future reward.
- [00:00:06.52 - 00:00:19.48] Remember, the discount factor controls how much future rewards matter.
- [00:00:13.04 - 00:00:19.48] The homework is due on Friday.

## Search results

### discount factor homework

- [00:00:06.52] Remember, the discount factor controls how much future rewards matter. (score 0.400)
- [00:00:13.04] The homework is due on Friday. (score 0.333)


```json
[
  {
    "stage": "validation",
    "event": "completed",
    "latency_ms": 41.59
  },
  {
    "stage": "model_inference",
    "event": "completed",
    "latency_ms": 1621.61
  },
  {
    "stage": "postprocessing",
    "event": "completed",
    "latency_ms": 0.3
  },
  {
    "stage": "retrieval",
    "event": "completed",
    "latency_ms": 0.17
  },
  {
    "stage": "run",
    "event": "finished",
    "latency_ms": 1758.35,
    "status": "ok"
  }
]
```

## planning

Run folder: `examples/verified/runs/20261023T005039-8368cab6`

Status: ok; elapsed: 1403.71 ms

Input: `examples/media/planning.mp4`; search: `battery encrypted`

# SecureNote - automatic candidate notes

Review against the recording. Extractive baseline; speaker identity is unknown.
Timestamps identify containing ASR segments, not exact sentence boundaries.

## Decisions

- [00:00:02.38 - 00:00:06.74] We agreed to keep the original recording on an encrypted drive.

## Action items

- [00:00:06.74 - 00:00:11.02] The device must record audio before sending it to the laptop.
- [00:00:11.02 - 00:00:14.34] Bob will review the microphone settings tomorrow.

## Questions

- [00:00:17.46 - 00:00:20.02] Who will test the transfer cable?

## Key points

- [00:00:00.00 - 00:00:02.38] This is the recorder planning meeting.
- [00:00:14.34 - 00:00:17.46] The important constraint is battery life.
- [00:00:20.02 - 00:00:22.82] We have not decided on a wireless connection.

## Search results

### battery encrypted

- [00:00:14.34] The important constraint is battery life. (score 0.354)
- [00:00:02.38] We agreed to keep the original recording on an encrypted drive. (score 0.289)


```json
[
  {
    "stage": "validation",
    "event": "completed",
    "latency_ms": 49.99
  },
  {
    "stage": "model_inference",
    "event": "completed",
    "latency_ms": 1286.52
  },
  {
    "stage": "postprocessing",
    "event": "completed",
    "latency_ms": 0.27
  },
  {
    "stage": "retrieval",
    "event": "completed",
    "latency_ms": 0.24
  },
  {
    "stage": "run",
    "event": "finished",
    "latency_ms": 1403.71,
    "status": "ok"
  }
]
```

## malformed_model_output

Run folder: `examples/verified/runs/20261023T005040-494a0374`

Status: failed; elapsed: 1324.58 ms

```json
[
  {
    "stage": "validation",
    "event": "completed",
    "latency_ms": 48.92
  },
  {
    "stage": "model_inference",
    "event": "completed",
    "latency_ms": 1202.92
  },
  {
    "stage": "postprocessing",
    "event": "failed",
    "latency_ms": 0.06,
    "error_type": "ValueError"
  },
  {
    "stage": "run",
    "event": "failed",
    "error_type": "ValueError"
  },
  {
    "stage": "run",
    "event": "finished",
    "latency_ms": 1324.58,
    "status": "failed"
  }
]
```

## silence

Run folder: `examples/verified/runs/20261023T005042-3bdabd82`

Status: no_speech; elapsed: 337.49 ms

```json
[
  {
    "stage": "validation",
    "event": "completed",
    "latency_ms": 48.65
  },
  {
    "stage": "model_inference",
    "event": "completed",
    "latency_ms": 240.69
  },
  {
    "stage": "postprocessing",
    "event": "completed",
    "latency_ms": 0.08
  },
  {
    "stage": "retrieval",
    "event": "completed",
    "latency_ms": 0.12
  },
  {
    "stage": "run",
    "event": "finished",
    "latency_ms": 337.49,
    "status": "no_speech"
  }
]
```
