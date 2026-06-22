# Platform Documentation & Specifications (docs)

This directory hosts product requirements documents (PRD), developmental phase planning, mathematical research references, and engineering walkthrough logs.

---

## 📊 Document Lifecycle Diagrams

### 1. Project Phase Rollout Flowchart
Describes the sequential implementation phases tracked inside this folder:

```mermaid
flowchart TD
    PRD["DeepHedging PRD (PRD_v2_Python)"] --> Plan["Phase 5 Start Plan (phase5_start_plan.md)"]
    Plan --> Ingest["C++ Core & API Ingestion"]
    Ingest --> Dev["Development & Testing Logs"]
    Dev --> WT["Walkthroughs (walkthrough_live_trading.md)"]
```

### 2. High-Level Design (HLD)
Groups documentation files by domain context:

```mermaid
graph TD
    subgraph ProductSpecs ["Product Specifications & PRDs"]
        PRD_PDF["DeepHedging_Platform_PRD_v2_Python.pdf"]
        PRD_TXT["DeepHedging_Platform_PRD_v2_Python.txt"]
    end

    subgraph ResearchPapers ["Research & Concept Notebooks"]
        AdvHedge["AdversialDeepHedging.pdf (Math paper)"]
        HFTCode["HFT_CAMP_CODE.ipynb (Notebook mockup)"]
    end

    subgraph MilestonePlanning ["Milestones & Walkthrough Logs"]
        Phases["Phases.md"]
        Phase5Plan["phase5_start_plan.md"]
        WT_Live["walkthrough_live_trading.md"]
        WT_P5["walkthrough_phase5.md"]
        WT_Gen["walkthrough.md"]
    end
```

### 3. Development Ingestion Sequence
Visualizes the pipeline for updating platform specs from PRD design to validation walkthroughs:

```mermaid
sequenceDiagram
    autonumber
    participant PM as Product Manager
    participant Dev as Engineering Team
    participant Git as Version Control
    participant WT as Walkthrough Logs

    PM->>Git: Push PRD & planning milestones (docs/Phases.md)
    activate Git
    Dev->>Git: Read requirements & implementation guidelines
    Note over Dev: Develop C++ backtester,<br/>FastAPI routing, and Next.js UI
    Dev->>WT: Write validation runs (walkthrough_live_trading.md)
    WT-->>Git: Commit walkthrough verifications
    deactivate Git
```

---

## 🗂️ Documentation Folder Structure

```
docs/
├── AdversialDeepHedging.pdf             # Academic paper detailing minimax robust hedging logic
├── DeepHedging_Platform_PRD_v2_Python.pdf # Platform Product Requirements Document (PDF)
├── DeepHedging_Platform_PRD_v2_Python.txt # Plain text version of the PRD
├── HFT_CAMP_CODE.ipynb                  # Prototyping notebook for high frequency deep hedging
├── Phases.md                            # Detailed development roadmap milestones list
├── new_chat_brief.md                    # Platform context outline for LLM context resumption
├── phase5_start_plan.md                 # Detailed deployment schedule for Phase 5
├── steps.md                             # Step-by-step checklist of build commands
├── walkthrough.md                       # High-level walkthrough of components
├── walkthrough_live_trading.md          # Verification steps for live options trading gateway
└── walkthrough_phase5.md                # Phase 5 checklist execution summary log
```
