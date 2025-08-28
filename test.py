flowchart TD
  UA[Mobile or Web App<br/>Camera and form] -->|"Photos and metadata"| API[API Gateway]
  API --> UP[Upload Service<br/>presigned URLs]
  UP --> OBJ[(Object Storage<br/>images and video)]
  API --> MD[Metadata Service<br/>device model TAC answers]
  MD --> MDB[(Metadata DB)]

  UP --> IQC[Image Quality Classifier<br/>blur low light occlusion]
  IQC -->|fail| GUIDE[On device guidance<br/>angle light focus]
  GUIDE --> UA
  IQC -->|pass| DEVREC[Device Recognition<br/>TAC match plus vision]
  DEVREC --> FBU[Feature Builder]

  UP --> DET[Damage and Accessory Detector<br/>cracks scratches missing items]
  DET --> FBU

  UA --> ST[Self Test Services<br/>mic speaker camera sensors]
  ST --> FBU

  MDB --> FBU
  OBJ --> FBU

  FBU --> FSTORE[(Feature Store)]
  FBU --> EB((Event Bus))
  EB --> Q4[Queue to valuation]

  %% Early payout preview
  FBU --> PREVAL[Pre valuation Service]
  PREVAL --> OFFER[Offer Builder<br/>price range and confidence]
  OFFER --> UI[Offer Card in app]
  UI -->|accept| SCHED[Schedule pickup]
  UI -->|counter or decline| LOOP[Request more photos or adjust answers]

  FBU --> LOG[(Observability<br/>metrics and traces)]
--------------------------------

flowchart TD
  FSTORE[(Feature Store)] --> COND[Condition Grader<br/>CV model grades A–D]
  OBJ[(Object Storage)] --> COND
  MDB[(Metadata DB)] --> COND

  COND --> PARTS[Component Predictors<br/>screen crack scratches battery accessories]
  PARTS --> FEATS[Feature Joiner]

  FEATS --> PRC[Price Recommender<br/>gradient boosting]
  FEATS --> RC[Refurb Cost Estimator]
  FEATS --> RISK[Risk and Fraud Model]
  FEATS --> CONF[Confidence Estimator]

  PRC --> POL[Pricing Policy Engine]
  RC --> POL
  RISK --> POL
  CONF --> POL

  POL --> OFFER2[Offer Builder<br/>instant payout or QC path]
  OFFER2 --> ODB[(Offers DB)]
  OFFER2 --> NOTIF[Notify app]

  OFFER2 -->|confidence >= threshold| INSTANT[Instant payout path<br/>payment orchestration]
  OFFER2 -->|confidence < threshold| QC[QC payout path<br/>warehouse verification]

  HIL[Human review UI] --> ODB
  HIL --> LABELS[(Label Store)]
  QC --> LABELS
  LABELS --> TMS[(Training Data Lake)]
  TMS --> REG[(Model Registry and Experiments)]
  REG --> COND
  REG --> PRC
  REG --> RISK
  REG --> MON[(Monitoring and drift)]
  FEATS --> MON
  INSTANT --> MON
  QC --> MON
