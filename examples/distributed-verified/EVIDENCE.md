# Two-role prototype evidence

Separate recorder and receiver processes; actual local HTTP upload and local model inference.

## business

Input: business.wav; bytes: 826348
Job: completed; pipeline: ok
Capture/transfer/processing wall time: 1786.84 ms

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

### decision action deadline important definition risk question

- [00:00:10.38] The main risk is limited storage on the recording device. (score 0.408)


## lecture

Input: lecture.mp3; bytes: 98238
Job: completed; pipeline: ok
Capture/transfer/processing wall time: 1981.86 ms

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

### decision action deadline important definition risk question

- [00:00:00.00] A policy map sustained to an action. (score 0.522)


## planning

Input: planning.mp4; bytes: 225989
Job: completed; pipeline: ok
Capture/transfer/processing wall time: 1603.99 ms

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

### decision action deadline important definition risk question

- [00:00:14.34] The important constraint is battery life. (score 0.500)


## Intentional failure

One upload byte was changed after the manifest checksum was computed. The receiver returned HTTP 400; no processing job was published, and the device copy remained queued. See evidence.json and laptop/receiver.jsonl for the measured result.
