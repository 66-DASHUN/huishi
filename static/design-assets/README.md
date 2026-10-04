# 绘世运行时设计资产库

本目录存放前端页面运行时可以直接调用的设计图片资源。

## 调用规则

前端通过 `manifest.json` 中的 `assetKey` 查找真实图片路径，不直接硬编码图片文件路径。

只有 `status` 为 `approved` 的资源可以被页面调用。

## 推荐目录

```text
static/design-assets/
  manifest.json
  home/
  workspace/
  assets/
  detail/
  auth/
  admin/
```

## 推荐 key

```text
home.hero
workspace.loading
workspace.reference.empty
workspace.generation.failed
assets.card.hover
auth.login.hero
admin.records.empty
```

## 角色职责

- UI/UX 设计：产出图片、命名资源、更新 manifest。
- 前端工程师：通过 assetKey 调用资源，确认运行时可用。
- 测试 QA：按 assetKey 和已批准图片做页面验收。
- 产品经理：确认图片符合已确认需求。
