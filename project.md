# NexMarket AI
## AI-Powered Marketing Automation Platform using Deep Learning, Generative AI, Predictive Analytics, and Workflow Automation

## 1. Project Overview

NexMarket AI is an end-to-end AI-powered marketing automation platform designed to help businesses create, publish, analyze, and optimize digital marketing campaigns from a single system.

The platform combines Generative AI, Vision Language Models, Natural Language Processing, Machine Learning, Deep Learning, Reinforcement Learning concepts, automatic social media publishing, and workflow automation.

A business owner provides campaign information such as product name, description, offer, target audience, campaign goal, theme, brand style, preferred platform, and posting schedule. NexMarket AI uses this information to generate marketing creatives, evaluate them, publish them, collect campaign feedback, predict customer and campaign behavior, and recommend future actions.

The project is designed as a modular and resource-aware system that can run local AI models on consumer-grade hardware. Transformer-based models use 4-bit quantization where supported, while a dynamic Model Manager loads and unloads large models as required to control GPU memory usage.

---

## 2. Problem Statement

Businesses, startups, and educational organizations often need to perform multiple marketing activities manually or through separate tools. These activities include:

- Creating promotional posters
- Writing advertisements and captions
- Evaluating marketing creatives
- Understanding customer feedback
- Identifying high-value leads
- Predicting campaign engagement
- Selecting effective marketing platforms and posting times
- Publishing content and tracking results

This fragmented workflow increases manual effort, operational cost, and decision-making time.

NexMarket AI addresses this problem by bringing these activities together into one intelligent, automated workflow.

---

## 3. Main Objectives

- Automatically generate marketing posters from campaign information.
- Generate platform-specific advertising content.
- Evaluate generated posters for visual and marketing quality.
- Analyze customer comments and feedback using NLP.
- Predict customer lead or purchase probability.
- Forecast future campaign engagement using LSTM.
- Recommend campaign strategies using an optimization algorithm.
- Automatically publish campaigns to supported social media platforms.
- Orchestrate the complete workflow using n8n.
- Efficiently execute large local AI models using quantization and dynamic model loading.

---

## 4. End-to-End Workflow

```text
                         User / Business Owner
                                  |
                                  v
                        Campaign Information
                                  |
                                  v
                         n8n Workflow Trigger
                                  |
                                  v
                         Campaign Context
                                  |
                                  v
                         Qwen2.5-3B Instruct
                                  |
                                  v
                  Structured Visual Specification
                                  |
                                  v
                         Stable Diffusion XL
                                  |
                                  v
                         Generated Visual Asset
                                  |
                                  v
                       Poster Composition Engine
                                  |
                                  +----------------+
                                  |                |
                                  v                v
                               Brand            Offer / CTA
                                  |                |
                                  +-------+--------+
                                          |
                                          v
                                  Final Marketing Poster
                                          |
                                          v
                                  Qwen2.5-VL-3B
                                          |
                                          v
                              Poster Quality Evaluation
                                          |
                              +-----------+-----------+
                              |                       |
                           APPROVE                   FAIL
                              |                       |
                              v                       v
                     Automatic Social Post       Regeneration
                              |                       |
                              v                       v
                     Campaign Analytics      Improved Visual Spec
                              |                       |
                +-------------+-------------+         |
                |             |             |         |
                v             v             v         |
         Sentiment       Lead Prediction    LSTM       |
         DistilBERT       XGBoost         Forecast     |
                |             |             |         |
                +-------------+-------------+---------+
                                          |
                                          v
                             Campaign Optimization
                                  Contextual Bandit
                                          |
                                          v
                             Dashboard & Reports
```

---

## 5. Core System Modules

### Module 1: Campaign Input and Context Creation

The user provides:

- Product name
- Product description
- Brand name
- Offer
- Target audience
- Campaign goal
- Theme
- Brand style
- Preferred platform
- Posting schedule
- Call-to-action

The raw information is converted into a normalized campaign context that is shared across the relevant modules.

### Module 2: AI Poster Generator

The poster generator creates campaign visuals using Stable Diffusion XL.

The system does not ask the diffusion model to render exact marketing text. Instead, the visual-generation stage focuses on imagery, scene, composition, lighting, mood, and campaign context.

### Module 3: Advertisement Generator

Qwen2.5-3B Instruct generates channel-specific marketing copy such as:

- Instagram caption
- Facebook advertisement
- LinkedIn post
- Email content
- Headline
- Call-to-action variants

### Module 4: Poster Composition Engine

The generated visual is converted into a final marketing poster by programmatically adding exact campaign information:

- Brand name
- Campaign title
- Offer
- Supporting text
- CTA
- Logo, when supplied by the user

The composition engine controls text wrapping, font size, safe margins, alignment, and placement so that important information is not clipped.

### Module 5: Poster Evaluation

Qwen2.5-VL-3B evaluates the final composed poster together with the campaign context.

The evaluator checks:

- Campaign relevance
- Product relevance
- Target-audience relevance
- Campaign-goal alignment
- Theme relevance
- Brand visibility
- Offer visibility
- Text readability
- Layout quality
- Marketing effectiveness

It returns a quality score, strengths, weaknesses, suggestions, and a decision such as approve, improve, or regenerate.

### Module 6: Sentiment Analysis

Customer reviews and social media comments are analyzed using DistilBERT.

Output:

- Positive
- Negative
- Neutral
- Confidence score

### Module 7: Lead Prediction

Customer interaction data is processed using XGBoost to estimate the likelihood of conversion.

Typical inputs include:

- Clicks
- Views
- Impressions
- Time spent
- Previous purchases
- Campaign/platform information

Output:

- Lead score
- Purchase probability
- Hot / Warm / Cold classification

### Module 8: Engagement Forecasting

A PyTorch LSTM model analyzes historical time-series campaign data and forecasts future engagement.

Forecast targets can include:

- Reach
- Likes
- Shares
- Comments
- Click-through rate
- Engagement rate

### Module 9: Campaign Optimization

A Contextual Multi-Armed Bandit is used to select or recommend marketing actions based on campaign context and previous outcomes.

Possible actions include:

- Social media platform
- Posting time
- Budget allocation
- Creative variant

The system uses campaign outcomes as feedback and improves future recommendations.

### Module 10: Automatic Social Media Publishing

The platform supports automatic posting or scheduling of approved campaign content.

The social publishing layer follows an adapter-based design so platform-specific implementation remains separate from the main application.

Supported or planned integrations include:

- Instagram
- Facebook
- LinkedIn
- X

A mock/demo adapter is also available when live credentials or platform permissions are unavailable.

### Module 11: n8n Workflow Engine

n8n acts as the central workflow orchestration layer. It coordinates:

- Campaign triggers
- AI service calls
- Poster generation
- Poster evaluation
- Publishing jobs
- Analytics collection
- Scheduled forecasting
- Optimization jobs
- Report generation
- Retry and failure handling

n8n performs orchestration; AI inference remains inside the FastAPI AI services.

---

## 6. Architecture

### High-Level Architecture

```text
+--------------------------------------------------------------+
|                    Next.js Frontend                          |
| Campaign UI | Poster Preview | Analytics | Reports          |
+----------------------------+---------------------------------+
                             |
                             v
+--------------------------------------------------------------+
|                     FastAPI Backend                          |
| API Routes | Authentication | Business Logic | Services     |
+----------------------------+---------------------------------+
                             |
                             v
+--------------------------------------------------------------+
|                    AI Service Layer                          |
| Poster | Ad Copy | Vision | Sentiment | Lead | LSTM | RL    |
+----------------------------+---------------------------------+
                             |
                             v
+--------------------------------------------------------------+
|                    Dynamic Model Manager                     |
| Lazy Load | Quantization | Device Selection | Unload | GC    |
+----------------------------+---------------------------------+
                             |
              +--------------+--------------+
              |              |              |
              v              v              v
        Qwen2.5-3B       SDXL          Qwen2.5-VL-3B
        4-bit NF4        FP16          4-bit NF4
              |
              +--------------+--------------+
                             |
              +--------------+--------------+
              |              |              |
              v              v              v
         DistilBERT      XGBoost        PyTorch LSTM
              |
              +--------------+--------------+
                             |
                             v
+--------------------------------------------------------------+
|                     PostgreSQL                               |
| Campaigns | Posters | Ads | Analytics | Leads | Forecasts   |
| Evaluations | Posts | Recommendations | Logs                |
+--------------------------------------------------------------+
                             |
                             v
+--------------------------------------------------------------+
|                        n8n                                    |
| Event Automation | Scheduling | Publishing | Reporting      |
+--------------------------------------------------------------+
```

---

## 7. Technology Stack

### Frontend

- Next.js 15
- React.js
- TypeScript
- Tailwind CSS
- shadcn/ui
- Recharts

### Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy

### Database

- PostgreSQL

### Workflow Automation

- n8n

### Deep Learning and AI

- PyTorch
- Hugging Face Transformers
- Hugging Face Diffusers
- Stable Diffusion XL

### Quantization and Model Optimization

- BitsAndBytes
- 4-bit NF4 quantization
- FP16 inference where appropriate
- Accelerate
- Dynamic model load/unload
- GPU memory cleanup

### Machine Learning

- XGBoost
- Scikit-learn

### Development and Deployment

- Git
- GitHub
- Docker
- Visual Studio Code
- Swagger/OpenAPI through FastAPI

---

## 8. Models Used

| Module | Model | Main Purpose |
|---|---|---|
| Poster Generation | Stable Diffusion XL | Generate campaign visuals |
| Advertisement Generation | Qwen2.5-3B Instruct | Generate marketing copy |
| Poster Evaluation | Qwen2.5-VL-3B | Evaluate final poster in context |
| Sentiment Analysis | DistilBERT | Classify customer sentiment |
| Lead Prediction | XGBoost | Predict conversion likelihood |
| Engagement Forecasting | PyTorch LSTM | Forecast future engagement |
| Campaign Optimization | Contextual Multi-Armed Bandit | Select/recommend campaign actions |

---

## 9. Algorithms Used

### 9.1 Generative AI

Generative models are used to create new marketing assets from campaign information.

- Text generation using Qwen2.5-3B Instruct
- Image generation using Stable Diffusion XL

### 9.2 Vision-Language Evaluation

Qwen2.5-VL compares the generated poster with the supplied campaign context and produces structured evaluation results.

### 9.3 Transformer-Based Sentiment Classification

DistilBERT performs contextual text classification of customer comments into sentiment categories.

### 9.4 XGBoost Classification

Gradient-boosted decision trees are used for structured customer behavior and lead prediction.

### 9.5 LSTM Time-Series Forecasting

Long Short-Term Memory networks model temporal dependencies in historical campaign activity to forecast future engagement.

### 9.6 Contextual Multi-Armed Bandit

The optimizer treats marketing actions as arms and uses context plus reward feedback to favor actions expected to improve campaign outcomes.

### 9.7 Dynamic Model Lifecycle Management

A resource-management algorithm controls model execution:

```text
Request
  -> Check Model Cache
  -> Load Required Model
  -> Run Inference
  -> Save Output
  -> Unload Model
  -> Clear GPU Cache
  -> Ready for Next Model
```

---

## 10. Quantization and Model Management

The target development hardware is a consumer laptop with an RTX 3050 Laptop GPU with 6 GB VRAM and 16 GB RAM.

To make local inference practical:

- Qwen2.5-3B uses 4-bit NF4 quantization.
- Qwen2.5-VL-3B uses 4-bit NF4 quantization where supported.
- Stable Diffusion XL uses FP16 and memory-saving techniques rather than 4-bit transformer quantization.
- Large models are loaded lazily.
- Only the required model is kept on the GPU during large-model inference.
- Models are unloaded after use.
- CUDA cache is cleared and garbage collection is triggered when appropriate.

This reduces peak VRAM demand and allows multiple AI capabilities to operate on limited hardware without permanently keeping all large models in GPU memory.

---

## 11. n8n Workflow Design

### Workflow A: Campaign Creation

```text
New Campaign
    |
    v
Generate Visual Specification
    |
    v
Generate Poster Visual
    |
    v
Generate Advertisement Copy
    |
    v
Compose Final Poster
    |
    v
Evaluate Poster
    |
    v
Approved?
   / \
 Yes  No
  |    |
  v    v
Publish  Regenerate
```

### Workflow B: Automatic Posting

```text
Approved Campaign
      |
      v
Check Platform + Schedule
      |
      v
Social Media Adapter
      |
      v
Publish / Schedule
      |
      v
Store Post ID + Status
```

### Workflow C: Analytics Processing

```text
Scheduled Trigger
      |
      v
Collect Campaign Metrics
      |
      v
Store Analytics
      |
      +---------> Sentiment Analysis
      |
      +---------> Lead Prediction
      |
      +---------> LSTM Forecast
      |
      v
Optimization
      |
      v
Dashboard Update
```

### Workflow D: Reporting

```text
Scheduled Trigger
      |
      v
Fetch Campaign Data
      |
      v
Generate Summary
      |
      v
Create Report
      |
      v
Store / Deliver Report
```

---

## 12. Expected Input

Example campaign request:

```json
{
  "campaign_name": "Summer Product Sale",
  "brand_name": "Example Brand",
  "product_name": "Running Shoes",
  "product_category": "Sportswear",
  "description": "Lightweight running shoes for everyday training",
  "offer": "50% OFF",
  "target_audience": "College students and young professionals",
  "campaign_goal": "Increase product sales",
  "theme": "Modern energetic fitness",
  "preferred_platform": "Instagram",
  "brand_style": "Premium and dynamic",
  "call_to_action": "Shop Now"
}
```

The system must not hard-code this example. The same architecture should work for different products, audiences, themes, offers, and campaign goals.

---

## 13. Expected Output

### Generated Poster

A context-aware marketing poster containing:

- Relevant visual concept
- Correct product context
- Brand representation
- Exact campaign title
- Exact offer
- Clear CTA
- Platform-appropriate composition

### Advertisement Content

```text
Instagram Caption
Facebook Ad
LinkedIn Post
Email Copy
Headline
CTA Variants
```

### Poster Evaluation

```json
{
  "overall_score": 88,
  "campaign_relevance": 92,
  "product_relevance": 90,
  "audience_relevance": 86,
  "campaign_goal_alignment": 89,
  "theme_relevance": 91,
  "brand_visibility": 85,
  "offer_visibility": 90,
  "text_readability": 87,
  "layout_quality": 88,
  "marketing_effectiveness": 89,
  "decision": "approve",
  "suggestions": []
}
```

### Lead Prediction

```text
Lead Score: 87/100
Purchase Probability: 0.84
Category: Hot Lead
```

### Sentiment Analysis

```text
Positive: 72%
Neutral: 18%
Negative: 10%
```

### Engagement Forecast

```text
Predicted Reach: 15,000
Predicted CTR: 7.2%
Predicted Engagement Rate: 8.4%
```

### Campaign Optimization

```text
Recommended Platform: Instagram
Recommended Posting Time: 7:00 PM
Recommended Budget: ₹500/day
Recommended Creative: Variant 2
```

### Social Publishing

```text
Platform: Instagram
Status: Published
Post ID: <platform-generated-id>
Published At: <timestamp>
```

---

## 14. Expected Final User Experience

The user should be able to:

1. Create a campaign from the dashboard.
2. Enter product and campaign details.
3. Start the automated pipeline.
4. See generation progress.
5. Preview generated creative assets.
6. View poster quality evaluation.
7. Approve or allow controlled regeneration.
8. Automatically publish the approved campaign.
9. View campaign analytics.
10. View customer sentiment.
11. View lead predictions.
12. View LSTM engagement forecasts.
13. View campaign optimization recommendations.
14. Track publication status and campaign history.

---

## 15. Database Entities

The persistent data layer should contain entities similar to:

- Users
- Campaigns
- Campaign Assets
- Posters
- Advertisement Copies
- Poster Evaluations
- Social Posts
- Campaign Analytics
- Customer Comments
- Sentiment Results
- Lead Predictions
- Engagement Forecasts
- Optimization Recommendations
- Workflow Execution Logs
- Model Metadata

Relationships should allow every prediction and recommendation to be traced back to the campaign and the data used to produce it.

---

## 16. Non-Functional Requirements

### Performance

- Efficient GPU memory usage
- Controlled model loading
- Low unnecessary frontend computation
- Reasonable AI response times

### Reliability

- Retry failed workflow steps
- Handle model-loading failures
- Handle missing social credentials
- Prevent infinite regeneration loops
- Preserve workflow logs

### Security

- Store secrets in environment variables
- Do not commit API keys or access tokens
- Validate user input
- Protect authenticated endpoints

### Maintainability

- Modular services
- Clear API contracts
- Adapter-based social integrations
- Central Model Manager
- Structured logging

### Scalability

The system should allow AI services, social platforms, and model versions to be replaced or extended without redesigning the complete application.

---

## 17. Project Completion Definition

A fully completed NexMarket AI implementation should demonstrate:

- Working campaign creation interface
- Working Generative AI poster pipeline
- Working advertisement generation
- Working Vision AI poster evaluation
- Working sentiment analysis
- Working XGBoost lead prediction
- Working LSTM engagement forecasting
- Working campaign optimization
- Automatic or demonstrably simulated social media publishing
- Working PostgreSQL persistence
- Working n8n orchestration
- Dynamic model loading/unloading
- 4-bit quantized transformer inference
- Analytics dashboard
- Testing evidence
- Deployment documentation

---

## 18. Final Project Outcome

The expected final system is a complete AI marketing automation platform rather than a collection of independent AI demos.

```text
                NEXMARKET AI
                     |
        +------------+------------+
        |                         |
   CREATE CAMPAIGN          AUTOMATE WORKFLOW
        |                         |
        v                         v
   Generate Poster             n8n
   Generate Ad Copy              |
   Evaluate Poster               v
        |                 Publish + Monitor
        +------------+------------+
                     |
                     v
                ANALYZE DATA
                     |
        +------------+------------+
        |            |            |
     Sentiment     Leads       LSTM
        |            |            |
        +------------+------------+
                     |
                     v
                OPTIMIZE
                     |
                     v
             BUSINESS INSIGHTS
                     |
                     v
             DASHBOARD / REPORTS
```

The final objective is to demonstrate a context-aware, resource-efficient, locally deployable AI platform capable of automating the marketing lifecycle from **campaign creation to content generation, evaluation, publishing, analytics, forecasting, optimization, and reporting**.
