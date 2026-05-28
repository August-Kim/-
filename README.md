# 글투 (글로벌 투자 통합 대시보드)

NASDAQ 100 · KOSPI 500 · 관세청 무역통계를 매일 자동 수집해서  
GitHub Pages에서 실시간으로 보여주는 투자 분석 대시보드.

---

## 구조

```
글투-dashboard/
├── .github/workflows/update_data.yml  # 매일 08:30 KST 자동 실행
├── data/latest.json                   # 자동 생성 (건드리지 않아도 됨)
├── scripts/collect_data.py            # 데이터 수집 스크립트
├── index.html                         # 대시보드 프론트엔드
└── requirements.txt
```

---

## 1단계 — 로컬에서 먼저 테스트

```bash
# 의존성 설치
pip install -r requirements.txt

# 데이터 수집 실행 (data/latest.json 생성됨)
python scripts/collect_data.py

# 브라우저에서 확인 (로컬 서버 필요)
python -m http.server 8000
# → http://localhost:8000 접속
```

---

## 2단계 — GitHub 저장소 세팅

```bash
git init
git add .
git commit -m "init: 글투 대시보드"
git remote add origin https://github.com/YOUR_ID/글투-dashboard.git
git push -u origin main
```

---

## 3단계 — GitHub Pages 활성화

1. 저장소 → **Settings** → **Pages**
2. Source: `Deploy from a branch`
3. Branch: `main` / `/ (root)`
4. **Save** 클릭
5. `https://YOUR_ID.github.io/글투-dashboard/` 에서 확인

---

## 4단계 — 관세청 API 키 등록 (선택)

API 키 없어도 동작하지만, 있으면 실시간 데이터로 자동 전환됩니다.

1. [관세청 UNI-PASS 포털](https://unipass.customs.go.kr/openapi/) 회원가입 후 API 키 발급
2. 저장소 → **Settings** → **Secrets and variables** → **Actions**
3. `New repository secret`
   - Name: `CUSTOMS_API_KEY`
   - Value: 발급받은 API 키 붙여넣기

---

## 자동 업데이트 주기

| 항목 | 주기 | 방법 |
|------|------|------|
| NASDAQ / KOSPI PER | **매일 08:30 KST** | GitHub Actions + yfinance |
| 무역통계 | **매일 08:30 KST** | 관세청 API 또는 fallback |

수동 실행: 저장소 → **Actions** → `글투 데이터 자동 업데이트` → **Run workflow**
