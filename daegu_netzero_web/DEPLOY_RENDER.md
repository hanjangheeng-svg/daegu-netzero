# 외부 접속용 배포 — Render + GitHub (단일 URL)

이 패키지는 React 프런트엔드와 FastAPI 백엔드를 **하나의 Docker 웹서비스**로 묶습니다. 무료 제공 여부 및 리소스 제한은 Render 가입 화면에서 확인하세요. 현재 시점에 배포가 완료되었다고 주장할 수 없으며, GitHub/Render 업로드는 사용자가 해야 합니다.

## 가장 빠른 배포 순서
1. GitHub에서 **새 공개 저장소**를 만듭니다. 저장소 이름 예: `daegu-netzero-demo`. 실제 기업 기밀 데이터를 업로드하지 마세요.
2. 이 `daegu_netzero_web` 폴더 **안의 내용 전체**(`Dockerfile`, `render.yaml`, `backend`, `frontend`, `data`, `requirements.txt` 등)를 저장소 최상위에 업로드합니다. ZIP 파일 자체만 업로드하면 실행되지 않습니다.
3. [Render](https://dashboard.render.com/)에서 `New` → `Web Service` → GitHub 저장소 연결 → **Runtime: Docker** 선택합니다. `Dockerfile`이 저장소 최상위에 있어야 합니다. 인스턴스는 이용 가능한 플랜을 선택하세요.
4. 서비스를 생성하면 빌드 로그에서 `npm run build`와 `pip install` 완료를 확인합니다. Render가 발급한 **실제 `https://...onrender.com` 주소**를 복사하세요. 주소는 임의로 만들 수 없습니다.
5. 접속 후 `/api/health` 경로에서 `{"status":"ok","mode":"local-rules"}` 반환을 확인합니다. 대시보드 → 사업장 진단 → 공정열 분석 → 경제성 → ZIP 다운로드를 시연하세요.
6. 대회 제출 메일에 발급받은 URL을 기재하고, 보고서 PDF와 소스 ZIP도 함께 첨부하세요.

## 주의
- 무료 인스턴스에서는 비활성 시 첫 접근이 느릴 수 있습니다. 마감 전에 **공개 URL을 시크릿 창으로** 직접 열어 확인하세요.
- 웹 입력은 외부 호스팅 서버로 전송됩니다(외부 LLM API로 보내지는 않음). **실제 사업장 기밀값을 넣지 마세요**. 서버에는 입력값 저장 로직이 없지만 플랫폼 로그 및 보유 정책은 별도입니다.
- 내부 계산 검증과 실제 현장 성능 검증은 구분합니다.
- GitHub 업로드 후 서비스 주소가 나오기 전에는 배포 성공이나 웹 공개를 주장할 수 없습니다.
- 외부 접속이 안 돼도 보고서 PDF와 전체 소스 ZIP을 기한 내 제출하는 것이 우선입니다.
