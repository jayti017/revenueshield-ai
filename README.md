# 🛡️ RevenueShield AI

### Intelligent Payment Recovery & Revenue Protection

> **Don't just predict payment failure. Decide what to do next.**

RevenueShield AI is an intelligent payment decision system that helps merchants reduce revenue loss from failed payments.

Instead of blindly retrying a failed transaction, RevenueShield evaluates **payment risk, customer history, recovery actions, expected revenue, merchant constraints, and safety rules** to select the most appropriate action.

---

## 🚀 Why RevenueShield?

A failed payment doesn't always need a retry.

Depending on the customer and transaction, the best action could be:

- 🟢 **Do Nothing**
- 🔄 **Retry**
- 🔔 **Send Reminder**
- 🔗 **Send Recovery Link**

RevenueShield compares these actions and chooses the one with the **best expected outcome while respecting merchant rules and safety constraints**.

---

## 🧠 How It Works

```text
Customer + Transaction
        ↓
   FastAPI Backend
        ↓
     Risk Model
        ↓
    Action Models
        ↓
   Decision Engine
        ↓
    Safety Layer
        ↓
    Audit Database
        ↓
   Final Decision
```

### The system considers:

**Risk** → How likely is the payment to fail?

**Expected Revenue** → Which action has the highest expected recovery?

**Merchant Rules** → Which actions are actually permitted?

**Safety** → Is the recommendation safe and reliable?

**Auditability** → Can we trace why the decision was made?

---

## 🔥 Example

For a high-risk customer:

```text
Failure Risk        → 48.7%
Recovery Link       → 76.8% success probability
Expected Revenue    → ₹7,683.40
Final Decision      → Send Recovery Link
```

Instead of blindly retrying, RevenueShield converts **risk prediction into an actionable revenue decision**.

---

## 🛡️ Built for Real-World Decisions

RevenueShield also handles:

- **Merchant action constraints**
- **Cold-start / new customers**
- **Low-confidence predictions**
- **Conservative safety fallbacks**
- **Decision auditing**
- **Razorpay TEST Mode integration**

Every important decision can be traced through the audit system.

---

## 💳 Payment Integration

RevenueShield integrates with **Razorpay TEST Mode** to demonstrate the complete payment lifecycle:

```text
Test Payment
     ↓
Razorpay
     ↓
FastAPI
     ↓
RevenueShield
     ↓
Risk + Decision
     ↓
Verified Result
```

> ⚠️ Razorpay is configured in **TEST MODE only**. No real money is involved.

---

## 🧰 Tech Stack

**Backend:** Python • FastAPI • Pydantic  
**ML:** Scikit-learn • Risk & Action Models  
**Frontend:** React • TypeScript • Tailwind CSS • Vite  
**Database:** SQLite  
**Payments:** Razorpay Test API  
**Testing:** Pytest  
**Development:** Git • GitHub

---

## 📊 Verified

```text
83 automated tests passing
Frontend production build passing
Razorpay TEST payment verified
Safety Layer verified
Audit persistence verified
5 end-to-end demo scenarios verified
```

---

## ▶️ Run Locally

### Backend

```bash
cd backend
uvicorn app.main:app --reload --env-file .env
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
pytest
```

### Production Build

```bash
cd frontend
npm run build
```

---

## 🎯 The Vision

Revenue recovery shouldn't be:

> **"Payment failed → Retry."**

It should be:

> **"Payment failed → Understand the risk → Evaluate the options → Choose the smartest safe action."**

### **RevenueShield AI**
**Smart Decisions. Protected Revenue.** 🛡️
