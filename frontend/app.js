"use strict";

const elements = {
  messages: document.getElementById("messages"),
  active: document.getElementById("activeStep"),
  anytimeMessages: document.getElementById("anytimeMessages"),
  scroll: document.getElementById("chatScroll"),
  queryForm: document.getElementById("queryForm"),
  queryInput: document.getElementById("queryInput"),
  menuButton: document.getElementById("menuButton"),
  notice: document.getElementById("notice"),
  statusText: document.getElementById("statusText"),
  toasts: document.getElementById("toastRegion"),
};

const expenseFields = [
  ["groceries", "Groceries"],
  ["travel", "Travel"],
  ["medfit", "Medical & fitness"],
  ["lep", "Loan EMI & insurance/premium"],
  ["monthly_rent", "Monthly rent"],
  ["m_bills", "Utility & household bills"],
  ["fashion", "Fashion"],
  ["entertainment", "Entertainment"],
  ["education", "Education"],
  ["emsaving", "Emergency savings"],
  ["miscellaneous", "Miscellaneous"],
];

const additionalTypes = {
  STOCK: "Stock",
  INVESTEMENTS: "Investments",
  BUSINESS: "Business",
  OTHERS: "Others",
};

const initialMessages = [
  {
    role: "assistant",
    text: "Welcome to FinTrack AI. I can guide your complete financial journey inside this chat.",
  },
];

const savedSession = readSession();
const state = {
  token: savedSession.token || null,
  user: savedSession.user || null,
  messages: Array.isArray(savedSession.messages) && savedSession.messages.length
    ? savedSession.messages.slice(-80)
    : initialMessages,
  anytimeMessages: Array.isArray(savedSession.anytimeMessages)
    ? savedSession.anytimeMessages.slice(-20)
    : [],
  flow: savedSession.token ? "main" : "welcome",
  mode: null,
  draft: null,
  selected: null,
  data: null,
  signup: null,
};

class APIError extends Error {
  constructor(message, status = 0, code = "api_error", details = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function readSession() {
  try {
    return JSON.parse(sessionStorage.getItem("fintrack-chat-session") || "{}") || {};
  } catch (_error) {
    return {};
  }
}

function saveSession() {
  sessionStorage.setItem(
    "fintrack-chat-session",
    JSON.stringify({
      token: state.token,
      user: state.user,
      messages: state.messages.slice(-80),
      anytimeMessages: state.anytimeMessages.slice(-20),
    }),
  );
}

function node(tag, className = "", text = "") {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== "") item.textContent = text;
  return item;
}

function addMessage(role, text) {
  const message = { role, text: String(text) };
  const last = state.messages[state.messages.length - 1];
  if (!last || last.role !== message.role || last.text !== message.text) {
    state.messages.push(message);
    state.messages = state.messages.slice(-80);
    saveSession();
  }
}

function messageRow(message) {
  const row = node("div", `message-row ${message.role}`);
  if (message.role === "assistant") row.append(node("div", "avatar", "AI"));
  row.append(node("div", "bubble", message.text));
  return row;
}

function renderMessages() {
  elements.messages.replaceChildren(...state.messages.map(messageRow));
}

function addAnytimeMessage(role, text) {
  state.anytimeMessages.push({ role, text: String(text) });
  state.anytimeMessages = state.anytimeMessages.slice(-20);
  saveSession();
}

function renderAnytimeMessages() {
  elements.anytimeMessages.replaceChildren(...state.anytimeMessages.map(messageRow));
}

function controlPanel(title, copy = "") {
  elements.active.replaceChildren();
  const row = node("div", "message-row control-row");
  row.append(node("div", "avatar", "AI"));
  const bubble = node("div", "bubble control-bubble");
  bubble.append(node("h2", "control-title", title));
  if (copy) bubble.append(node("p", "control-copy", copy));
  row.append(bubble);
  elements.active.append(row);
  return bubble;
}

function loadingPanel(copy = "Working on it") {
  const bubble = controlPanel(copy);
  const typing = node("div", "typing");
  typing.append(node("i"), node("i"), node("i"));
  bubble.append(typing);
}

function actionGrid(single = false) {
  return node("div", `action-grid${single ? " single" : ""}`);
}

function actionButton(label, handler, options = {}) {
  const button = node("button", `action-button${options.danger ? " danger" : ""}`, label);
  button.type = "button";
  button.addEventListener("click", () => runAction(button, handler));
  return button;
}

async function runAction(button, handler) {
  const buttons = elements.active.querySelectorAll("button");
  buttons.forEach((item) => { item.disabled = true; });
  try {
    await handler();
  } catch (error) {
    showInlineError(error instanceof APIError ? error.message : "Something went wrong. Please try again.");
  } finally {
    if (document.body.contains(button)) {
      buttons.forEach((item) => { item.disabled = false; });
    }
  }
}

function showInlineError(message) {
  const current = elements.active.querySelector(".control-bubble");
  if (!current) return;
  current.querySelectorAll(".callout.error").forEach((item) => item.remove());
  current.prepend(callout(message, "error"));
  scrollToBottom();
}

function callout(text, type = "") {
  return node("div", `callout${type ? ` ${type}` : ""}`, text);
}

function toast(text) {
  const item = node("div", "toast", text);
  elements.toasts.append(item);
  window.setTimeout(() => item.remove(), 3200);
}

function scrollToBottom() {
  window.requestAnimationFrame(() => {
    elements.scroll.scrollTop = elements.scroll.scrollHeight;
  });
}

function transition(flow, options = {}) {
  if (options.user) addMessage("user", options.user);
  if (options.assistant) addMessage("assistant", options.assistant);
  state.flow = flow;
  if (options.clear) {
    state.mode = null;
    state.draft = null;
    state.selected = null;
    state.data = null;
  }
  render();
}

function resetAuthenticatedFlow() {
  state.mode = null;
  state.draft = null;
  state.selected = null;
  state.data = null;
  transition("main");
}

function clearAuthentication(message = null) {
  state.token = null;
  state.user = null;
  state.signup = null;
  state.mode = null;
  state.draft = null;
  state.selected = null;
  state.data = null;
  state.flow = "welcome";
  if (message) addMessage("assistant", message);
  saveSession();
}

async function request(path, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let response;
  try {
    response = await fetch(path, {
      method: options.method || "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch (_error) {
    throw new APIError("The FinTrack service is unavailable. Please retry in a moment.", 0, "network_error");
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch (_error) {
    payload = null;
  }
  if (!response.ok) {
    const apiError = payload && payload.error ? payload.error : {};
    if (response.status === 401 && state.token) {
      clearAuthentication("Your session has ended. Please log in again.");
      render();
    }
    throw new APIError(
      apiError.message || "The request could not be completed.",
      response.status,
      apiError.code,
      apiError.details || {},
    );
  }
  return payload;
}

async function optionalGet(path) {
  try {
    return await request(path);
  } catch (error) {
    if (error instanceof APIError && error.status === 404) return null;
    throw error;
  }
}

function field(label, name, type = "text", value = "", options = {}) {
  const wrapper = node("div", `field${options.full ? " full" : ""}`);
  const inputId = `field-${name}-${Math.random().toString(16).slice(2)}`;
  const labelNode = node("label", "", label);
  labelNode.htmlFor = inputId;
  const input = document.createElement("input");
  input.id = inputId;
  input.name = name;
  input.type = type;
  input.value = value ?? "";
  input.required = options.required !== false;
  if (options.min !== undefined) input.min = String(options.min);
  if (options.max !== undefined) input.max = String(options.max);
  if (options.step !== undefined) input.step = String(options.step);
  if (options.autocomplete) input.autocomplete = options.autocomplete;
  wrapper.append(labelNode, input);
  return wrapper;
}

function selectField(label, name, choices, selected, options = {}) {
  const wrapper = node("div", `field${options.full ? " full" : ""}`);
  const inputId = `field-${name}-${Math.random().toString(16).slice(2)}`;
  const labelNode = node("label", "", label);
  labelNode.htmlFor = inputId;
  const select = document.createElement("select");
  select.id = inputId;
  select.name = name;
  for (const [value, display] of choices) {
    const option = node("option", "", display);
    option.value = value;
    option.selected = value === selected;
    select.append(option);
  }
  wrapper.append(labelNode, select);
  return wrapper;
}

function formActions(primaryLabel, secondary = []) {
  const actions = node("div", "form-actions");
  const submit = node("button", "primary-button", primaryLabel);
  submit.type = "submit";
  actions.append(submit);
  for (const item of secondary) {
    const button = node("button", "secondary-button", item.label);
    button.type = "button";
    button.addEventListener("click", item.handler);
    actions.append(button);
  }
  return actions;
}

function summaryList(rows) {
  const list = node("div", "summary-list");
  for (const [label, value] of rows) {
    const item = node("div", "summary-item");
    item.append(node("span", "", label), node("strong", "", String(value)));
    list.append(item);
  }
  return list;
}

function dataTable(headers, rows) {
  const table = node("table", "data-table");
  const head = node("thead");
  const headerRow = node("tr");
  headers.forEach((header) => headerRow.append(node("th", "", header)));
  head.append(headerRow);
  const body = node("tbody");
  for (const row of rows) {
    const rowNode = node("tr");
    row.forEach((value) => rowNode.append(node("td", "", String(value))));
    body.append(rowNode);
  }
  table.append(head, body);
  return table;
}

function metricGrid(metrics) {
  const grid = node("div", "metric-grid");
  for (const [label, value] of metrics) {
    const card = node("div", "metric-card");
    card.append(node("span", "", label), node("strong", "", String(value)));
    grid.append(card);
  }
  return grid;
}

function barChart(values, formatter = formatINR) {
  const valid = values.map(([, amount]) => Math.max(0, Number(amount) || 0));
  const maximum = Math.max(...valid, 1);
  const chart = node("div", "chart");
  values.forEach(([label, raw], index) => {
    const amount = Number(raw) || 0;
    const row = node("div", "chart-row");
    const track = node("div", "bar-track");
    const fill = node("div", "bar-fill");
    fill.style.width = `${Math.max(2, (valid[index] / maximum) * 100)}%`;
    track.append(fill);
    row.append(node("span", "", label), track, node("span", "chart-value", formatter(amount)));
    chart.append(row);
  });
  return chart;
}

function formatINR(value) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value) || 0);
}

function shortDate(value) {
  return String(value || "").slice(0, 10);
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function futureISO(days = 365) {
  const value = new Date();
  value.setDate(value.getDate() + days);
  return value.toISOString().slice(0, 10);
}

function renderWelcome() {
  const bubble = controlPanel("What would you like to do?", "Choose a guided journey, or type any question in the composer below.");
  const actions = actionGrid();
  actions.append(
    actionButton("Log in", () => transition("login", { user: "Log in", assistant: "Enter your account details below." })),
    actionButton("Create an account", () => transition("signup", { user: "Create an account", assistant: "Let's set up your account securely." })),
  );
  bubble.append(actions);
}

function renderLogin() {
  const bubble = controlPanel("Log in", "Use your registered email and password.");
  const form = node("form", "chat-form");
  const grid = node("div", "form-grid");
  grid.append(
    field("Email address", "email", "email", "", { full: true, autocomplete: "email" }),
    field("Password", "password", "password", "", { full: true, autocomplete: "current-password" }),
  );
  form.append(grid, formActions("Log in", [
    { label: "Create account", handler: () => transition("signup") },
    { label: "Cancel", handler: () => transition("welcome") },
  ]));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("button[type=submit]");
    await runAction(submit, async () => {
      const values = new FormData(form);
      const auth = await request("/api/auth/login", {
        method: "POST",
        body: { email: values.get("email"), password: values.get("password") },
      });
      state.token = auth.access_token;
      state.user = await request("/api/auth/me");
      saveSession();
      transition("main", {
        user: "Login submitted",
        assistant: `Welcome back, ${state.user.name}. Everything you need is available in this chat.`,
        clear: true,
      });
    });
  });
  bubble.append(form);
}

function renderSignup() {
  const bubble = controlPanel("Create your account", "You will review the non-sensitive details before the OTP is sent.");
  const form = node("form", "chat-form");
  const grid = node("div", "form-grid");
  grid.append(
    field("Full name", "name", "text", state.draft?.name || "", { full: true, autocomplete: "name" }),
    field("Email address", "email", "email", state.draft?.email || "", { full: true, autocomplete: "email" }),
    selectField("Gender", "gender", [
      ["Female", "Female"], ["Male", "Male"], ["Other", "Other"], ["Prefer not to say", "Prefer not to say"],
    ], state.draft?.gender || "Prefer not to say"),
    node("div"),
    field("Password", "password", "password", "", { autocomplete: "new-password" }),
    field("Confirm password", "confirm_password", "password", "", { autocomplete: "new-password" }),
  );
  form.append(grid, formActions("Review signup", [
    { label: "Back", handler: () => transition("welcome") },
  ]));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    if (values.password !== values.confirm_password) {
      showInlineError("Passwords do not match.");
      return;
    }
    state.draft = {
      ...values,
      name: values.name.trim(),
      email: values.email.trim().toLowerCase(),
    };
    transition("signup-confirm", { user: "Review my signup" });
  });
  bubble.append(form);
}

function renderSignupConfirm() {
  if (!state.draft) return transition("signup");
  const bubble = controlPanel("Confirm your signup", "Your password is deliberately excluded from this summary.");
  bubble.append(summaryList([
    ["Name", state.draft.name],
    ["Email", state.draft.email],
    ["Gender", state.draft.gender],
  ]));
  const actions = actionGrid();
  actions.append(
    actionButton("Confirm & send OTP", async () => {
      await request("/api/auth/signup/start", { method: "POST", body: state.draft });
      state.signup = { email: state.draft.email };
      transition("signup-otp", {
        user: "Signup confirmed",
        assistant: "A four-digit verification code was sent. Enter it below within five minutes.",
      });
    }),
    actionButton("Edit details", () => transition("signup")),
    actionButton("Cancel", () => {
      state.draft = null;
      transition("welcome");
    }, { danger: true }),
  );
  bubble.append(actions);
}

function renderSignupOtp() {
  if (!state.signup || !state.draft) return transition("signup");
  const bubble = controlPanel("Verify your email", "Verification attempts and resends are protected by limits.");
  const form = node("form", "chat-form");
  form.append(
    field("Four-digit OTP", "otp", "password", "", { full: true, min: 0, max: 9999 }),
    formActions("Verify OTP", [
      {
        label: "Resend OTP",
        handler: () => runAction(form.querySelector("button[type=button]"), async () => {
          await request("/api/auth/signup/start", { method: "POST", body: state.draft });
          toast("A new verification code was sent.");
        }),
      },
      {
        label: "Cancel",
        handler: () => {
          state.signup = null;
          state.draft = null;
          transition("welcome");
        },
      },
    ]),
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("button[type=submit]");
    await runAction(submit, async () => {
      const values = new FormData(form);
      const auth = await request("/api/auth/signup/verify", {
        method: "POST",
        body: { email: state.signup.email, otp: values.get("otp") },
      });
      state.token = auth.access_token;
      state.user = auth.user;
      state.signup = null;
      state.draft = null;
      saveSession();
      transition("main", {
        user: "OTP submitted",
        assistant: `Your account is ready, ${state.user.name}. What would you like to do first?`,
        clear: true,
      });
    });
  });
  bubble.append(form);
}

function renderMain() {
  const name = state.user?.name ? `, ${state.user.name}` : "";
  const bubble = controlPanel(`Main menu${name}`, "Choose an action. Your account identity is taken from the secure session.");
  const actions = actionGrid();
  actions.append(
    actionButton("Income profile", () => transition("income-menu", { user: "Income profile", clear: true })),
    actionButton("Expense profile", () => transition("expense-menu", { user: "Expense profile", clear: true })),
    actionButton("Goals & savings", () => transition("goal-menu", { user: "Goals and savings", clear: true })),
    actionButton("Financial analytics", () => transition("analytics", { user: "Financial analytics", clear: true })),
    actionButton("Log out", () => transition("logout"), { danger: true }),
  );
  bubble.append(actions);
}

function renderIncomeMenu() {
  const bubble = controlPanel("Income profile", "Add historical snapshots, see the latest profile, or update it in place.");
  const actions = actionGrid();
  actions.append(
    actionButton("View latest income", async () => {
      state.selected = await request("/api/income/latest");
      transition("income-view", { user: "View latest income" });
    }),
    actionButton("Add new income profile", () => {
      state.mode = "add";
      state.selected = null;
      transition("income-form");
    }),
    actionButton("Update latest income", async () => {
      state.selected = await request("/api/income/latest");
      state.mode = "update";
      transition("income-form", { user: "Update latest income" });
    }),
    actionButton("Back to main menu", resetAuthenticatedFlow),
  );
  bubble.append(actions);
}

function incomeRows(value) {
  return [
    ["Income type", String(value.income_type || "").replaceAll("_", " ")],
    ["Monthly income", formatINR(value.monthly_income)],
    ["Additional income type", additionalTypes[value.additional_income_type] || value.additional_income_type],
    ["Additional monthly income", formatINR(value.additional_monthly_income)],
    ["Dependants", value.dependants],
  ];
}

function renderIncomeView() {
  if (!state.selected) return transition("income-menu");
  const bubble = controlPanel("Latest income profile", "This is the current snapshot used by analytics and recommendations.");
  bubble.append(summaryList(incomeRows(state.selected)));
  const actions = actionGrid();
  actions.append(
    actionButton("Update this profile", () => {
      state.mode = "update";
      transition("income-form");
    }),
    actionButton("Income menu", () => transition("income-menu")),
    actionButton("Main menu", resetAuthenticatedFlow),
  );
  bubble.append(actions);
}

function renderIncomeForm() {
  const update = state.mode === "update";
  const old = update ? state.selected || {} : {};
  const bubble = controlPanel(update ? "Update income profile" : "Add income profile", "All amounts are monthly INR values and may be zero.");
  const form = node("form", "chat-form");
  const grid = node("div", "form-grid");
  grid.append(
    selectField("Income type", "income_type", [
      ["SALARIED", "Salaried"], ["PROFESSIONAL", "Professional"], ["BUSINESS", "Business"], ["OTHERS", "Others"],
    ], old.income_type || "SALARIED"),
    field("Monthly income", "monthly_income", "number", old.monthly_income || 0, { min: 0, step: 0.01 }),
    selectField("Additional income type", "additional_income_type", Object.entries(additionalTypes), old.additional_income_type || "OTHERS"),
    field("Additional monthly income", "additional_monthly_income", "number", old.additional_monthly_income || 0, { min: 0, step: 0.01 }),
    field("Number of dependants", "dependants", "number", old.dependants || 0, { min: 0, max: 19, step: 1, full: true }),
  );
  form.append(grid, formActions("Review changes", [
    { label: "Back", handler: () => transition("income-menu") },
    { label: "Cancel", handler: resetAuthenticatedFlow },
  ]));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    state.draft = {
      income_type: values.income_type,
      monthly_income: Number(values.monthly_income),
      additional_income_type: values.additional_income_type,
      additional_monthly_income: Number(values.additional_monthly_income),
      dependants: Number(values.dependants),
    };
    transition("income-confirm", { user: "Review income details" });
  });
  bubble.append(form);
}

function renderIncomeConfirm() {
  if (!state.draft) return transition("income-menu");
  const update = state.mode === "update";
  const bubble = controlPanel("Confirm income details", update ? "The selected profile will be updated; no new row will be added." : "A new historical profile will be added.");
  if (update && state.selected) {
    const changes = incomeRows(state.draft).map(([label, value], index) => [label, incomeRows(state.selected)[index][1], value]);
    bubble.append(dataTable(["Field", "Previous", "New"], changes));
  } else {
    bubble.append(summaryList(incomeRows(state.draft)));
  }
  const actions = actionGrid();
  actions.append(
    actionButton("Confirm & save", async () => {
      state.selected = await request(update ? `/api/income/${state.selected.profile_id}` : "/api/income", {
        method: update ? "PUT" : "POST",
        body: state.draft,
      });
      state.draft = null;
      transition("income-success", { assistant: "Your income profile was saved successfully." });
    }),
    actionButton("Edit", () => transition("income-form")),
    actionButton("Cancel", resetAuthenticatedFlow, { danger: true }),
  );
  bubble.append(actions);
}

function renderIncomeSuccess() {
  const bubble = controlPanel("Income saved", "Your latest financial snapshot is ready.");
  bubble.append(summaryList(incomeRows(state.selected)));
  const actions = actionGrid();
  actions.append(
    actionButton("View profile", () => transition("income-view")),
    actionButton("Go to expenses", () => transition("expense-menu", { clear: true })),
    actionButton("Main menu", resetAuthenticatedFlow),
  );
  bubble.append(actions);
}

function renderExpenseMenu() {
  const bubble = controlPanel("Expense profile", "Track all eleven monthly categories without leaving this conversation.");
  const actions = actionGrid();
  actions.append(
    actionButton("View latest expenses", async () => {
      state.selected = await request("/api/expenses/latest");
      transition("expense-view", { user: "View latest expenses" });
    }),
    actionButton("Add new expense profile", () => {
      state.mode = "add";
      state.selected = null;
      transition("expense-form");
    }),
    actionButton("Update latest expenses", async () => {
      state.selected = await request("/api/expenses/latest");
      state.mode = "update";
      transition("expense-form", { user: "Update latest expenses" });
    }),
    actionButton("Back to main menu", resetAuthenticatedFlow),
  );
  bubble.append(actions);
}

function renderExpenseSummary(bubble, data) {
  bubble.append(metricGrid([["Total monthly expenses", formatINR(data.total_expenses ?? expenseFields.reduce((sum, [key]) => sum + Number(data[key] || 0), 0))]]));
  bubble.append(dataTable(
    ["Category", "Amount"],
    expenseFields.map(([key, label]) => [label, formatINR(data[key])]),
  ));
}

function renderExpenseView() {
  if (!state.selected) return transition("expense-menu");
  const bubble = controlPanel("Latest expense profile", "This snapshot powers your current analytics and goal recommendation.");
  renderExpenseSummary(bubble, state.selected);
  const actions = actionGrid();
  actions.append(
    actionButton("Update this profile", () => {
      state.mode = "update";
      transition("expense-form");
    }),
    actionButton("Expense menu", () => transition("expense-menu")),
    actionButton("Main menu", resetAuthenticatedFlow),
  );
  bubble.append(actions);
}

function renderExpenseForm() {
  const update = state.mode === "update";
  const old = update ? state.selected || {} : {};
  const bubble = controlPanel(update ? "Update expense profile" : "Add expense profile", "Zero is allowed. Negative values are rejected.");
  const form = node("form", "chat-form");
  const grid = node("div", "form-grid");
  expenseFields.forEach(([key, label]) => {
    grid.append(field(label, key, "number", old[key] || 0, { min: 0, step: 0.01 }));
  });
  form.append(grid, formActions("Review expenses", [
    { label: "Back", handler: () => transition("expense-menu") },
    { label: "Cancel", handler: resetAuthenticatedFlow },
  ]));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const values = new FormData(form);
    state.draft = Object.fromEntries(expenseFields.map(([key]) => [key, Number(values.get(key))]));
    transition("expense-confirm", { user: "Review expense details" });
  });
  bubble.append(form);
}

function renderExpenseConfirm() {
  if (!state.draft) return transition("expense-menu");
  const update = state.mode === "update";
  const total = expenseFields.reduce((sum, [key]) => sum + state.draft[key], 0);
  const bubble = controlPanel("Confirm expense details", update ? "The selected expense snapshot will be updated." : "A new historical expense snapshot will be added.");
  bubble.append(metricGrid([["New total", formatINR(total)]]));
  if (update && state.selected) {
    bubble.append(dataTable(
      ["Category", "Previous", "New"],
      expenseFields.map(([key, label]) => [label, formatINR(state.selected[key]), formatINR(state.draft[key])]),
    ));
  } else {
    bubble.append(dataTable(["Category", "Amount"], expenseFields.map(([key, label]) => [label, formatINR(state.draft[key])])));
  }
  const actions = actionGrid();
  actions.append(
    actionButton("Confirm & save", async () => {
      state.selected = await request(update ? `/api/expenses/${state.selected.expense_id}` : "/api/expenses", {
        method: update ? "PUT" : "POST",
        body: state.draft,
      });
      state.draft = null;
      transition("expense-success", { assistant: "Your expense profile was saved successfully." });
    }),
    actionButton("Edit", () => transition("expense-form")),
    actionButton("Cancel", resetAuthenticatedFlow, { danger: true }),
  );
  bubble.append(actions);
}

function renderExpenseSuccess() {
  const bubble = controlPanel("Expenses saved", "Here is a quick view of your largest monthly categories.");
  const top = expenseFields
    .map(([key, label]) => [label, Number(state.selected[key] || 0)])
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);
  bubble.append(metricGrid([["Total expenses", formatINR(state.selected.total_expenses)]]));
  bubble.append(barChart(top));
  const actions = actionGrid();
  actions.append(
    actionButton("View full profile", () => transition("expense-view")),
    actionButton("Go to goals", () => transition("goal-menu", { clear: true })),
    actionButton("Main menu", resetAuthenticatedFlow),
  );
  bubble.append(actions);
}

function renderGoalMenu() {
  const bubble = controlPanel("Goals & monthly savings", "Create and update goals, record contributions, or inspect progress history.");
  const actions = actionGrid();
  actions.append(
    actionButton("View my goals", () => transition("goal-list", { user: "View my goals" })),
    actionButton("Create a goal", async () => {
      const [income, expenses] = await Promise.all([
        optionalGet("/api/income/latest"), optionalGet("/api/expenses/latest"),
      ]);
      if (!income || !expenses) {
        state.data = { missingIncome: !income, missingExpenses: !expenses };
        transition("goal-prerequisites");
        return;
      }
      state.mode = "add";
      state.selected = null;
      transition("goal-form", { user: "Create a goal" });
    }),
    actionButton("Update a goal", () => {
      state.mode = "update";
      transition("goal-select");
    }),
    actionButton("Record monthly savings", () => {
      state.mode = "history-add";
      transition("goal-select");
    }),
    actionButton("View goal history", () => {
      state.mode = "history-view";
      transition("goal-select");
    }),
    actionButton("Back to main menu", resetAuthenticatedFlow),
  );
  bubble.append(actions);
}

function renderGoalPrerequisites() {
  const bubble = controlPanel("Complete your setup first", "A current income and expense profile are required for a safe recommendation.");
  bubble.append(callout("The chatbot can take you directly to the missing step.", "warning"));
  const actions = actionGrid();
  if (state.data?.missingIncome) {
    actions.append(actionButton("Add income profile", () => {
      state.mode = "add";
      state.selected = null;
      transition("income-form", { clear: false });
    }));
  }
  if (state.data?.missingExpenses) {
    actions.append(actionButton("Add expense profile", () => {
      state.mode = "add";
      state.selected = null;
      transition("expense-form", { clear: false });
    }));
  }
  actions.append(actionButton("Back to goals", () => transition("goal-menu")));
  bubble.append(actions);
}

function goalRows(goals) {
  return goals.map((goal) => [
    `${goal.goal_name} · #${goal.goal_id}`,
    formatINR(goal.goal_amount),
    formatINR(goal.monthly_saving_target),
    `${Number(goal.progress_percent || 0).toFixed(1)}%`,
    goal.goal_status,
  ]);
}

async function renderGoalList() {
  loadingPanel("Loading your goals");
  try {
    const goals = await request("/api/goals");
    state.data = goals;
    const bubble = controlPanel("My goals", goals.length ? "Progress includes every recorded monthly saving." : "No goals have been created yet.");
    if (goals.length) {
      bubble.append(dataTable(["Goal", "Amount", "Monthly target", "Progress", "Status"], goalRows(goals)));
    } else {
      bubble.append(callout("Start with a goal once your income and expense setup is complete."));
    }
    const actions = actionGrid();
    actions.append(
      actionButton("Create a goal", () => transition("goal-menu")),
      actionButton("Goals menu", () => transition("goal-menu")),
      actionButton("Main menu", resetAuthenticatedFlow),
    );
    bubble.append(actions);
    scrollToBottom();
  } catch (error) {
    const bubble = controlPanel("Goals unavailable");
    bubble.append(callout(error.message || "Could not load goals.", "error"));
    bubble.append(actionButton("Try again", () => renderGoalList()));
  }
}

async function renderGoalSelect() {
  loadingPanel("Loading your goals");
  try {
    const goals = await request("/api/goals");
    const titles = {
      update: "Select a goal to update",
      "history-add": "Select a goal for this saving entry",
      "history-view": "Select a goal to view its history",
    };
    const bubble = controlPanel(titles[state.mode] || "Select a goal");
    if (!goals.length) {
      bubble.append(callout("You do not have a goal yet.", "warning"));
      bubble.append(actionButton("Back to goals", () => transition("goal-menu")));
      return;
    }
    const form = node("form", "chat-form");
    const options = goals.map((goal) => [String(goal.goal_id), `${goal.goal_name} · ID ${goal.goal_id} · ${goal.goal_status}`]);
    form.append(
      selectField("Goal", "goal_id", options, options[0][0], { full: true }),
      formActions("Continue", [{ label: "Back", handler: () => transition("goal-menu") }]),
    );
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const selectedId = Number(new FormData(form).get("goal_id"));
      state.selected = goals.find((goal) => goal.goal_id === selectedId);
      if (state.mode === "update") transition("goal-form");
      if (state.mode === "history-add") transition("history-form");
      if (state.mode === "history-view") transition("history-list");
    });
    bubble.append(form);
    scrollToBottom();
  } catch (error) {
    const bubble = controlPanel("Goals unavailable");
    bubble.append(callout(error.message || "Could not load goals.", "error"));
    bubble.append(actionButton("Back", () => transition("goal-menu")));
  }
}

function renderGoalForm() {
  const update = state.mode === "update";
  const old = update ? state.selected || {} : {};
  const bubble = controlPanel(update ? "Update goal" : "Create a goal", "First calculate the recommendation. Nothing is saved until the next confirmation step.");
  const form = node("form", "chat-form");
  const grid = node("div", "form-grid");
  grid.append(
    field("Goal name", "goal_name", "text", old.goal_name || "", { full: true }),
    field("Goal amount", "goal_amount", "number", old.goal_amount || 1000, { min: 0.01, step: 0.01, full: true }),
    field("Start date", "start_date", "date", shortDate(old.start_date) || todayISO()),
    field("End date", "end_date", "date", shortDate(old.end_date) || futureISO()),
    selectField("Status", "goal_status", [
      ["ACTIVE", "Active"], ["PAUSED", "Paused"], ["ACHIEVED", "Achieved"], ["EXPIRED", "Expired"], ["INACTIVE", "Inactive"],
    ], old.goal_status || "ACTIVE", { full: true }),
  );
  form.append(grid, formActions("Calculate recommendation", [
    { label: "Back", handler: () => transition("goal-menu") },
    { label: "Cancel", handler: resetAuthenticatedFlow },
  ]));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("button[type=submit]");
    await runAction(submit, async () => {
      const values = Object.fromEntries(new FormData(form));
      state.draft = { ...values, goal_amount: Number(values.goal_amount) };
      state.data = await request("/api/goals/recommendation", { method: "POST", body: state.draft });
      if (state.data.missing_prerequisites?.length) {
        state.data = {
          missingIncome: state.data.missing_prerequisites.includes("income"),
          missingExpenses: state.data.missing_prerequisites.includes("expenses"),
        };
        transition("goal-prerequisites");
        return;
      }
      transition("goal-confirm", { user: "Show my goal recommendation" });
    });
  });
  bubble.append(form);
}

function renderGoalConfirm() {
  if (!state.draft || !state.data) return transition("goal-menu");
  const update = state.mode === "update";
  const recommendation = state.data;
  const bubble = controlPanel("Review goal & recommendation", "Confirm only after checking the dates, amount, and safe monthly target.");
  bubble.append(summaryList([
    ["Goal", state.draft.goal_name],
    ["Amount", formatINR(state.draft.goal_amount)],
    ["Date range", `${state.draft.start_date} → ${state.draft.end_date}`],
    ["Status", state.draft.goal_status],
  ]));
  bubble.append(metricGrid([
    ["Recommended monthly saving", formatINR(recommendation.recommended_monthly_saving)],
    ["Estimated duration", recommendation.estimated_duration_months ? `${recommendation.estimated_duration_months} months` : "Not currently feasible"],
  ]));
  bubble.append(callout(recommendation.message, recommendation.feasible ? "" : "warning"));
  (recommendation.warnings || []).forEach((warning) => bubble.append(callout(warning, "warning")));
  const actions = actionGrid();
  actions.append(
    actionButton("Confirm & save", async () => {
      state.selected = await request(update ? `/api/goals/${state.selected.goal_id}` : "/api/goals", {
        method: update ? "PUT" : "POST",
        body: state.draft,
      });
      state.draft = null;
      transition("goal-success", { assistant: "Your goal was saved successfully." });
    }),
    actionButton("Edit", () => transition("goal-form")),
    actionButton("Cancel", resetAuthenticatedFlow, { danger: true }),
  );
  bubble.append(actions);
}

function renderGoalSuccess() {
  const goal = state.selected;
  const bubble = controlPanel("Goal saved", "Your plan is ready for monthly saving entries.");
  bubble.append(metricGrid([
    ["Goal amount", formatINR(goal.goal_amount)],
    ["Monthly target", formatINR(goal.monthly_saving_target)],
  ]));
  const actions = actionGrid();
  actions.append(
    actionButton("Record monthly savings", () => {
      state.mode = "history-add";
      transition("history-form");
    }),
    actionButton("View my goals", () => transition("goal-list")),
    actionButton("Main menu", resetAuthenticatedFlow),
  );
  bubble.append(actions);
}

function renderHistoryForm() {
  if (!state.selected) return transition("goal-menu");
  const bubble = controlPanel("Record monthly savings", `Contribution for ${state.selected.goal_name} · ID ${state.selected.goal_id}`);
  const form = node("form", "chat-form");
  const grid = node("div", "form-grid");
  grid.append(
    field("Saving date/month", "saving_date", "date", todayISO()),
    field("Amount saved", "amount_saved", "number", 1000, { min: 0.01, step: 0.01 }),
  );
  form.append(grid, formActions("Review saving entry", [
    { label: "Back", handler: () => transition("goal-menu") },
    { label: "Cancel", handler: resetAuthenticatedFlow },
  ]));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(form));
    state.draft = { saving_date: values.saving_date, amount_saved: Number(values.amount_saved) };
    transition("history-confirm", { user: "Review saving entry" });
  });
  bubble.append(form);
}

function renderHistoryConfirm() {
  if (!state.draft || !state.selected) return transition("goal-menu");
  const bubble = controlPanel("Confirm saving entry", "Exact duplicate entries are rejected automatically.");
  bubble.append(summaryList([
    ["Goal", `${state.selected.goal_name} · ID ${state.selected.goal_id}`],
    ["Saving date", state.draft.saving_date],
    ["Amount saved", formatINR(state.draft.amount_saved)],
  ]));
  const actions = actionGrid();
  actions.append(
    actionButton("Confirm & record", async () => {
      await request(`/api/goals/${state.selected.goal_id}/history`, { method: "POST", body: state.draft });
      state.selected = await request(`/api/goals/${state.selected.goal_id}`);
      state.draft = null;
      transition("history-success", { assistant: "Your monthly saving was recorded." });
    }),
    actionButton("Edit", () => transition("history-form")),
    actionButton("Cancel", resetAuthenticatedFlow, { danger: true }),
  );
  bubble.append(actions);
}

function renderHistorySuccess() {
  const bubble = controlPanel("Saving recorded", "Your goal progress has been updated.");
  bubble.append(metricGrid([
    ["Total saved", formatINR(state.selected.total_saved)],
    ["Goal progress", `${Number(state.selected.progress_percent || 0).toFixed(1)}%`],
  ]));
  const actions = actionGrid();
  actions.append(
    actionButton("View history", () => {
      state.mode = "history-view";
      transition("history-list");
    }),
    actionButton("Goals menu", () => transition("goal-menu")),
    actionButton("Main menu", resetAuthenticatedFlow),
  );
  bubble.append(actions);
}

async function renderHistoryList() {
  if (!state.selected) return transition("goal-menu");
  loadingPanel("Loading saving history");
  try {
    const history = await request(`/api/goals/${state.selected.goal_id}/history`);
    const bubble = controlPanel(`${state.selected.goal_name} history`, "Entries are ordered by saving date.");
    if (history.length) {
      bubble.append(dataTable(
        ["Date", "Amount saved"],
        history.map((item) => [item.saving_date, formatINR(item.amount_saved)]),
      ));
    } else {
      bubble.append(callout("No monthly saving entries have been recorded yet."));
    }
    const actions = actionGrid();
    actions.append(
      actionButton("Record savings", () => {
        state.mode = "history-add";
        transition("history-form");
      }),
      actionButton("Goals menu", () => transition("goal-menu")),
      actionButton("Main menu", resetAuthenticatedFlow),
    );
    bubble.append(actions);
    scrollToBottom();
  } catch (error) {
    const bubble = controlPanel("History unavailable");
    bubble.append(callout(error.message || "Could not load goal history.", "error"));
    bubble.append(actionButton("Back", () => transition("goal-menu")));
  }
}

async function renderAnalytics() {
  loadingPanel("Preparing your financial analytics");
  try {
    const data = await request("/api/analytics/summary");
    state.data = data;
    const bubble = controlPanel("Financial analytics", "Every number below belongs only to your authenticated account.");
    bubble.append(metricGrid([
      ["Monthly income", formatINR(data.total_monthly_income)],
      ["Monthly expenses", formatINR(data.total_monthly_expenses)],
      ["Free cash flow", formatINR(data.free_cash_flow)],
      ["Total goal amount", formatINR(data.total_goal_amount)],
    ]));
    if (data.income_profile) {
      bubble.append(node("h3", "control-title", "Income composition"));
      bubble.append(barChart([
        ["Primary", data.income_profile.monthly_income],
        ["Additional", data.income_profile.additional_monthly_income],
      ]));
    }
    if (data.expense_profile) {
      bubble.append(node("h3", "control-title", "Expense breakdown"));
      bubble.append(barChart(expenseFields.map(([key, label]) => [label, data.expense_profile[key]])));
    }
    bubble.append(node("h3", "control-title", "Income vs expenses"));
    bubble.append(barChart([
      ["Income", data.total_monthly_income],
      ["Expenses", data.total_monthly_expenses],
      ["Free cash", Math.max(0, data.free_cash_flow)],
    ]));
    bubble.append(node("h3", "control-title", "Goal status distribution"));
    bubble.append(barChart(Object.entries(data.goal_status_counts), (value) => String(value)));
    if (data.goals.length) {
      bubble.append(node("h3", "control-title", "Goal progress"));
      bubble.append(dataTable(["Goal", "Amount", "Monthly target", "Progress", "Status"], goalRows(data.goals)));
    }
    (data.warnings || []).forEach((warning) => bubble.append(callout(warning, "warning")));
    const actions = actionGrid();
    if (!data.profile_completion.has_income) {
      actions.append(actionButton("Add income", () => {
        state.mode = "add";
        state.selected = null;
        transition("income-form");
      }));
    }
    if (!data.profile_completion.has_expenses) {
      actions.append(actionButton("Add expenses", () => {
        state.mode = "add";
        state.selected = null;
        transition("expense-form");
      }));
    }
    if (!data.profile_completion.has_goals) {
      actions.append(actionButton("Create a goal", () => transition("goal-menu")));
    }
    actions.append(
      actionButton("Refresh analytics", () => renderAnalytics()),
      actionButton("Main menu", resetAuthenticatedFlow),
    );
    bubble.append(actions);
    scrollToBottom();
  } catch (error) {
    const bubble = controlPanel("Analytics unavailable");
    bubble.append(callout(error.message || "Could not load analytics.", "error"));
    const actions = actionGrid();
    actions.append(actionButton("Try again", () => renderAnalytics()), actionButton("Main menu", resetAuthenticatedFlow));
    bubble.append(actions);
  }
}

function renderLogout() {
  const bubble = controlPanel("Log out?", "This revokes the current server-side session and clears this chat's sensitive state.");
  const actions = actionGrid();
  actions.append(
    actionButton("Confirm logout", async () => {
      await request("/api/auth/logout", { method: "POST", body: {} });
      clearAuthentication();
      state.messages = [{ role: "assistant", text: "You are logged out. Welcome back to FinTrack AI." }];
      state.anytimeMessages = [];
      saveSession();
      render();
    }, { danger: true }),
    actionButton("Cancel", () => transition("main")),
  );
  bubble.append(actions);
}

const renderers = {
  welcome: renderWelcome,
  login: renderLogin,
  signup: renderSignup,
  "signup-confirm": renderSignupConfirm,
  "signup-otp": renderSignupOtp,
  main: renderMain,
  "income-menu": renderIncomeMenu,
  "income-view": renderIncomeView,
  "income-form": renderIncomeForm,
  "income-confirm": renderIncomeConfirm,
  "income-success": renderIncomeSuccess,
  "expense-menu": renderExpenseMenu,
  "expense-view": renderExpenseView,
  "expense-form": renderExpenseForm,
  "expense-confirm": renderExpenseConfirm,
  "expense-success": renderExpenseSuccess,
  "goal-menu": renderGoalMenu,
  "goal-prerequisites": renderGoalPrerequisites,
  "goal-list": renderGoalList,
  "goal-select": renderGoalSelect,
  "goal-form": renderGoalForm,
  "goal-confirm": renderGoalConfirm,
  "goal-success": renderGoalSuccess,
  "history-form": renderHistoryForm,
  "history-confirm": renderHistoryConfirm,
  "history-success": renderHistorySuccess,
  "history-list": renderHistoryList,
  analytics: renderAnalytics,
  logout: renderLogout,
};

function render() {
  renderMessages();
  renderAnytimeMessages();
  elements.menuButton.classList.toggle("hidden", !state.token || state.flow === "main");
  elements.statusText.textContent = state.token && state.user
    ? `Signed in as ${state.user.name}`
    : "Secure financial assistant";
  const renderer = renderers[state.flow];
  if (!renderer) {
    state.flow = state.token ? "main" : "welcome";
    renderers[state.flow]();
  } else {
    renderer();
  }
  scrollToBottom();
}

elements.queryForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = elements.queryInput.value.trim();
  if (!query) return;
  elements.queryInput.value = "";
  addAnytimeMessage("user", query);
  addAnytimeMessage(
    "assistant",
    "Thanks for your question. General AI responses are coming soon. For now, I can record the query and keep guiding you through the available FinTrack actions.",
  );
  renderAnytimeMessages();
  scrollToBottom();
});

elements.menuButton.addEventListener("click", () => resetAuthenticatedFlow());

async function bootstrap() {
  elements.notice.classList.add("hidden");
  if (state.token) {
    try {
      state.user = await request("/api/auth/me");
      state.flow = "main";
      saveSession();
    } catch (error) {
      if (!(error instanceof APIError && error.status === 401)) {
        elements.notice.textContent = "The backend is temporarily unavailable. You can still view the chat, then retry shortly.";
        elements.notice.classList.remove("hidden");
      }
    }
  }
  render();
}

bootstrap();
