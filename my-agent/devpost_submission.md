## Inspiration
AI datacenters rely on highly skilled technicians to diagnose hardware issues and make high-stakes decisions quickly. We wanted to reduce that pressure by building a real-time video AI assistant that can support technicians directly in the field during live calls.

## What it does
**Synapse AI Ops** is a real-time troubleshooting assistant for GPU datacenter racks.  
Using live video, it can detect and read on-device text (like GPU labels), answer technician queries, and retrieve relevant GPU information to assist with diagnostics and decision-making.

## How we built it
We built Synapse AI Ops using:
- **AdaL coding agent** for rapid iteration and implementation
- **Stream Vision Agents** for real-time video/audio agent orchestration
- **Gemini Realtime + tool calling** for contextual responses
- OCR + retrieval pipelines for GPU-focused guidance

## Challenges we ran into
Troubleshooting in datacenters is a two-layer workflow:
1. **In-field technician** handling hardware physically
2. **Supervisor technician** validating and guiding remotely

Designing for both roles in real time was challenging. We addressed this by building two dedicated app flows—one optimized for field operations and one for remote supervision.

## Accomplishments that we're proud of
- Built **two role-specific solutions** in under 5 hours
- Integrated real-time video OCR with live agent responses
- Added retrieval/tool-calling flow for GPU-specific assistance
- Delivered an end-to-end working prototype under hackathon time pressure

## What we learned
- How to design low-latency, streaming-first AI systems
- How real-time tool calling improves reliability and usefulness
- How multimodal AI can meaningfully support operational workflows

## What’s next for Synapse AI Ops
- Unify both apps into one scalable platform
- Add deeper diagnostic analytics and reporting
- Expand the knowledge/retrieval layer for enterprise datacenter operations
- Improve reliability for production deployment across larger teams
