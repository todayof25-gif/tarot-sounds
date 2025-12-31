# Soul Roulette CDN 구조

## 목적
- 앱 업데이트 없이 룰렛 보상(아이템/뱃지)을 `tarot-sounds/` 기반 CDN으로 관리합니다.

## 폴더 구조
- `roulette/v1/manifest.json`: 보상 정의 + 월별 노출 풀
- `roulette/v1/items/<rewardId>/icon.(png|jpg|webp)`: 보상 아이콘

## 월별 노출 아이템 변경
1) `roulette/v1/manifest.json`의 `pools["YYYY-MM"]`에 해당 월에 노출할 `rewardId` 목록을 넣습니다.
2) 해당 키가 없으면 `pools["default"]`가 사용됩니다.

## 새 보상 추가(확장)
1) `roulette/v1/items/<rewardId>/` 폴더 생성
2) 아이콘 추가: `icon.png`(또는 `icon.jpg`)
3) `roulette/v1/manifest.json`의 `items[]`에 항목 추가
4) 원하는 월의 `pools["YYYY-MM"]` 또는 `default`에 `rewardId`를 포함

