document.querySelectorAll("form[data-confirm-delete]").forEach((formEl) => {
  formEl.addEventListener("submit", (event) => {
    const message = formEl.dataset.confirmDelete || "确认删除？";
    if (!window.confirm(message)) {
      event.preventDefault();
    }
  });
});

document.querySelectorAll("[data-admin-file-input]").forEach((input) => {
  const fileName = input.closest("form")?.querySelector("[data-admin-file-name]");
  input.addEventListener("change", () => {
    const file = input.files?.[0];
    if (fileName) fileName.textContent = file ? file.name : "未选择文件";
  });
});

document.querySelectorAll("[data-bulk-invite-form], [data-bulk-user-form]").forEach((formEl) => {
  const formId = formEl.getAttribute("id");
  const checkAll = formEl.closest(".admin-table-wrap")?.querySelector("[data-bulk-check-all]");
  const items = Array.from(document.querySelectorAll(`[data-bulk-item][form="${formId}"]`));
  const itemName = formEl.dataset.bulkUserForm !== undefined ? "用户" : "邀请码";

  function syncCheckAll() {
    if (!checkAll) return;
    const checkedCount = items.filter((item) => item.checked).length;
    checkAll.checked = items.length > 0 && checkedCount === items.length;
    checkAll.indeterminate = checkedCount > 0 && checkedCount < items.length;
  }

  checkAll?.addEventListener("change", () => {
    items.forEach((item) => {
      item.checked = checkAll.checked;
    });
    syncCheckAll();
  });

  items.forEach((item) => {
    item.addEventListener("change", syncCheckAll);
  });

  formEl.addEventListener("submit", (event) => {
    const submitter = event.submitter;
    const selectedCount = items.filter((item) => item.checked).length;
    if (selectedCount === 0) {
      event.preventDefault();
      window.alert(`请先选择${itemName}`);
      return;
    }
    const confirmMessage = submitter?.dataset?.confirmBulk;
    if (confirmMessage && !window.confirm(confirmMessage)) {
      event.preventDefault();
    }
  });

  syncCheckAll();
});

const userDrawer = document.querySelector("[data-user-edit-drawer]");
const userDrawerClose = document.querySelector("[data-user-edit-close]");
const editUserName = document.querySelector("[data-edit-user-name]");
const editUserMeta = document.querySelector("[data-edit-user-meta]");
const currentUserNote = document.querySelector("[data-current-user-note]");
const userActionForms = Array.from(document.querySelectorAll("[data-user-action-form]"));
const userEditToggles = Array.from(document.querySelectorAll("[data-user-edit-toggle]"));

function setUserActionUrls(userId) {
  userActionForms.forEach((formEl) => {
    const template = formEl.dataset.actionTemplate || "";
    formEl.setAttribute("action", template.replace("__USER_ID__", String(userId)));
  });
}

function openUserDrawer(row) {
  if (!userDrawer || !row) return;
  const userId = row.dataset.userId || "";
  const userName = row.dataset.userName || "未命名用户";
  const userUsername = row.dataset.userUsername || userName;
  const userRole = row.dataset.userRole || "user";
  const userEnabled = row.dataset.userEnabled === "1";
  const userPoints = row.dataset.userPoints || "0";
  const isCurrent = row.dataset.userCurrent === "1";

  editUserName.textContent = userName;
  editUserMeta.textContent = `#${userId} · ${userUsername} · ${userPoints} 点`;
  currentUserNote.hidden = !isCurrent;

  const roleSelect = userDrawer.querySelector("[data-user-role-form] select[name='role']");
  if (roleSelect) roleSelect.value = userRole;
  const statusToggle = userDrawer.querySelector("[data-user-status-form] input[name='enabled']");
  if (statusToggle) statusToggle.checked = userEnabled;

  setUserActionUrls(userId);
  userDrawer.hidden = false;
}

function closeUserDrawer() {
  if (!userDrawer) return;
  userDrawer.hidden = true;
  userEditToggles.forEach((toggle) => {
    toggle.checked = false;
  });
}

userEditToggles.forEach((toggle) => {
  toggle.addEventListener("change", () => {
    const row = toggle.closest("[data-user-row]");
    if (!row) return;
    if (toggle.checked) {
      userEditToggles.forEach((other) => {
        if (other !== toggle) other.checked = false;
      });
      openUserDrawer(row);
    } else {
      closeUserDrawer();
    }
  });
});

userDrawerClose?.addEventListener("click", closeUserDrawer);

document.addEventListener("click", (event) => {
  if (!userDrawer || userDrawer.hidden) return;
  if (event.target.closest("[data-user-edit-drawer]") || event.target.closest("[data-user-edit-toggle]")) return;
  if (!event.target.closest("[data-user-row]")) return;
});

const auditDrawer = document.querySelector("[data-audit-drawer]");
const auditBackdrop = document.querySelector("[data-audit-backdrop]");
const auditDrawerTitle = document.querySelector("[data-audit-title]");
const auditDrawerMeta = document.querySelector("[data-audit-meta]");
const auditBefore = document.querySelector("[data-audit-before]");
const auditAfter = document.querySelector("[data-audit-after]");
const auditDrawerClose = document.querySelector("[data-audit-close]");
let auditDrawerTrigger = null;

function formatAuditValue(rawValue) {
  if (!rawValue) return "{}";
  try {
    return JSON.stringify(JSON.parse(rawValue), null, 2);
  } catch (_error) {
    return rawValue;
  }
}

function openAuditDrawer(trigger) {
  if (!auditDrawer || !auditBackdrop) return;
  auditDrawerTrigger = trigger;
  auditDrawerTitle.textContent = trigger.dataset.action || "记录";
  auditDrawerMeta.textContent = trigger.dataset.meta || "";
  auditBefore.textContent = formatAuditValue(trigger.dataset.before);
  auditAfter.textContent = formatAuditValue(trigger.dataset.after);
  auditBackdrop.hidden = false;
  auditDrawer.hidden = false;
  document.body.classList.add("admin-drawer-open");
  auditDrawer.focus();
}

function closeAuditDrawer() {
  if (!auditDrawer || auditDrawer.hidden) return;
  auditDrawer.hidden = true;
  auditBackdrop.hidden = true;
  document.body.classList.remove("admin-drawer-open");
  if (auditDrawerTrigger) auditDrawerTrigger.focus();
  auditDrawerTrigger = null;
}

document.querySelectorAll("[data-audit-open]").forEach((trigger) => {
  trigger.addEventListener("click", () => openAuditDrawer(trigger));
});

auditDrawerClose?.addEventListener("click", closeAuditDrawer);
auditBackdrop?.addEventListener("click", closeAuditDrawer);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && auditDrawer && !auditDrawer.hidden) {
    closeAuditDrawer();
  }
});

const activityDrawer = document.querySelector("[data-activity-drawer]");
const activityBackdrop = document.querySelector("[data-activity-backdrop]");
const activityDrawerClose = document.querySelector("[data-activity-close]");
let activityDrawerTrigger = null;

function setActivityText(selector, value) {
  const target = activityDrawer?.querySelector(selector);
  if (target) target.textContent = value || "-";
}

function openActivityDrawer(trigger) {
  const row = trigger.closest("[data-activity-row]");
  if (!activityDrawer || !activityBackdrop || !row) return;
  let event;
  try {
    event = JSON.parse(row.dataset.activity || "{}");
  } catch (_error) {
    return;
  }
  activityDrawerTrigger = trigger;
  setActivityText("[data-activity-title]", event.event_label || "业务事件");
  setActivityText("[data-activity-user]", `${event.username || "-"}${event.user_id ? ` (#${event.user_id})` : ""}`);
  setActivityText("[data-activity-time]", event.occurred_at);
  setActivityText("[data-activity-status]", event.status_label || event.status);
  setActivityText("[data-activity-points]", `${Number(event.points_delta || 0) >= 0 ? "+" : ""}${Number(event.points_delta || 0)} 点`);
  setActivityText("[data-activity-links]", [event.record_id ? `记录 #${event.record_id}` : "", event.ledger_id ? `流水 #${event.ledger_id}` : ""].filter(Boolean).join(" · "));
  setActivityText("[data-activity-params]", [event.mode, event.resolution, event.actual_size, event.model_label || event.model_source].filter(Boolean).join(" · "));
  setActivityText("[data-activity-summary]", event.prompt || event.admin_note || event.summary);
  activityBackdrop.hidden = false;
  activityDrawer.hidden = false;
  document.body.classList.add("admin-drawer-open");
  activityDrawer.focus();
}

function closeActivityDrawer() {
  if (!activityDrawer || activityDrawer.hidden) return;
  activityDrawer.hidden = true;
  activityBackdrop.hidden = true;
  document.body.classList.remove("admin-drawer-open");
  activityDrawerTrigger?.focus();
  activityDrawerTrigger = null;
}

document.querySelectorAll("[data-activity-open]").forEach((trigger) => {
  trigger.addEventListener("click", () => openActivityDrawer(trigger));
});

activityDrawerClose?.addEventListener("click", closeActivityDrawer);
activityBackdrop?.addEventListener("click", closeActivityDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && activityDrawer && !activityDrawer.hidden) closeActivityDrawer();
});

document.querySelectorAll("[data-dialog-open]").forEach((trigger) => {
  trigger.addEventListener("click", () => {
    const dialog = document.getElementById(trigger.dataset.dialogOpen || "");
    if (dialog instanceof HTMLDialogElement) dialog.showModal();
  });
});

document.querySelectorAll(".settings-dialog").forEach((dialog) => {
  dialog.querySelectorAll("[data-dialog-close]").forEach((button) => {
    button.addEventListener("click", () => dialog.close());
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
});

document.querySelectorAll("form[data-confirm]").forEach((formEl) => {
  formEl.addEventListener("submit", (event) => {
    if (!window.confirm(formEl.dataset.confirm || "确认执行此操作？")) event.preventDefault();
  });
});
