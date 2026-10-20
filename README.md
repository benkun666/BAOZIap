# 包子漫画（重制版）— BandComic 自定义源 API

本项目按照 BandComic `CUSTOM_SOURCE.md` 的 `/config`、搜索、详情、章节图片列表接口格式搭建。

## Render 部署
1. 将 ZIP 解压后上传到自己的 GitHub 仓库。
2. Render 选择 New + → Web Service，连接仓库。
3. Build Command：`pip install -r requirements.txt`
4. Start Command：`gunicorn app:app --workers 2 --threads 4 --timeout 60`
5. 部署完成后打开 `https://你的服务.onrender.com/config`，确认返回 `baozi_recode` 配置。
6. 将服务根地址或 `/config` 地址按腕上漫画/同步器的说明添加。

## 可选环境变量
- `BAOZI_LANGUAGE`: `cn` 或 `tw`
- `BAOZI_DOMAIN`: `bzmgcn.com`、`baozimhcn.com`、`webmota.com`、`kukuc.co`、`twmanga.com`、`dinnerku.com`
- `BAOZI_CDN`: `as.baozimh.com`、`as2.baozimh.com`、`static-tw.bzmgcn.com`、`static-tw.baozimh.com`
- `BAOZI_IMAGE_QUALITY`: `/w640` 或空字符串

## 重要说明
这是一个初始适配模板，不是已验证可用的完整重制。你提供的 JavaScript 片段在登录代码中途截断；原站 HTML/API 的搜索、详情、章节选择器可能变化，所以需要在真实站点允许访问时测试并调整 `app.py` 中的解析逻辑。部署成功不等于上游解析已验证成功。


## 配置格式修正版
`/config` 的顶层键使用 `包子漫画（重制版）`，并按 BandComic 文档提供路径前缀：
- `detailPath`: `/album/`
- `photoPath`: `/photo//chapter/`
- `searchPath`: `/search//`

注意：站点 HTML/API 解析尚未经过真实线上测试；如果配置错误提示消失但搜索无结果或章节无图，需要继续根据实际页面结构适配。
