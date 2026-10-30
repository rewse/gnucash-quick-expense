"use strict";

// The credentials live only in this page's variables, for the requests
// that need them. Amounts stay strings end to end; the server parses them.

(() => {
  const $ = (id) => document.getElementById(id);

  const signInForm = $("sign-in");
  const signInButton = $("sign-in-button");
  const usernameInput = $("username");
  const passwordInput = $("password");
  const expenseForm = $("expense");
  const fields = $("expense-fields");
  const addButton = $("add-button");
  const amountInput = $("amount");
  const amountCurrency = $("amount-currency");
  const fromSelect = $("from");
  const toInput = $("to");
  const toOptions = $("to-options");
  const conversion = $("conversion");
  const toAmountInput = $("to-amount");
  const toCurrency = $("to-currency");
  const rateNote = $("rate-note");
  const dateInput = $("date");
  const descriptionInput = $("description");
  const statusLine = $("status");

  let credentials = null;
  let fromAccounts = [];
  let toAccounts = [];
  let activeOption = -1;
  let rateRequest = 0;
  let rateTimer = 0;

  // Full-width digits and punctuation from Japanese keyboards become ASCII,
  // and thousands separators are dropped.
  const cleanAmount = (text) => text.normalize("NFKC").replace(/,/g, "").trim();

  const today = () => {
    const now = new Date();
    const pad = (value) => String(value).padStart(2, "0");
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  };

  const showStatus = (message, kind) => {
    statusLine.textContent = message;
    statusLine.className = `status ${kind || ""}`.trim();
  };

  const post = async (path, body) => {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...credentials, ...body }),
      cache: "no-store",
      credentials: "omit",
    });
    let data = {};
    try {
      data = await response.json();
    } catch {
      // A proxy error page is not JSON; the status code is enough.
    }
    return { status: response.status, data };
  };

  const errorMessage = (result) => {
    if (result.status === 401) return "Wrong username or password.";
    if (result.status === 400 && result.data.error) return result.data.error;
    if (result.status === 413) return "The description is too long.";
    return "Could not add the expense. Try again.";
  };

  const accountFor = (list, path) => list.find((account) => account.path === path);
  const selectedFrom = () => accountFor(fromAccounts, fromSelect.value);
  const selectedTo = () => accountFor(toAccounts, toInput.value);

  const needsConversion = () => {
    const from = selectedFrom();
    const to = selectedTo();
    return Boolean(from && to && from.currency !== to.currency);
  };

  const updateAddButton = () => {
    const ready =
      credentials !== null &&
      cleanAmount(amountInput.value) !== "" &&
      selectedFrom() !== undefined &&
      selectedTo() !== undefined &&
      dateInput.value !== "" &&
      (!needsConversion() || cleanAmount(toAmountInput.value) !== "");
    addButton.disabled = !ready;
  };

  // --- The To combobox -----------------------------------------------------

  const matchingAccounts = () => {
    const query = toInput.value.trim().toLowerCase();
    return toAccounts.filter((account) => account.path.toLowerCase().includes(query));
  };

  const closeOptions = () => {
    toOptions.hidden = true;
    toInput.setAttribute("aria-expanded", "false");
    toInput.removeAttribute("aria-activedescendant");
    activeOption = -1;
  };

  const highlight = (index) => {
    const items = toOptions.querySelectorAll("li");
    items.forEach((item, i) => item.setAttribute("aria-selected", String(i === index)));
    activeOption = index;
    if (index >= 0 && items[index]) {
      toInput.setAttribute("aria-activedescendant", items[index].id);
      items[index].scrollIntoView({ block: "nearest" });
    } else {
      toInput.removeAttribute("aria-activedescendant");
    }
  };

  const chooseTo = (path) => {
    toInput.value = path;
    closeOptions();
    accountsChanged();
  };

  const openOptions = () => {
    const matches = matchingAccounts();
    toOptions.replaceChildren(
      ...matches.map((account, i) => {
        const item = document.createElement("li");
        item.id = `to-option-${i}`;
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", "false");
        item.textContent = account.path;
        // Keeps the focus in the input, which would otherwise blur and close
        // the list before the click. Choosing on click rather than here lets
        // a finger that lands on an option scroll the list instead.
        item.addEventListener("pointerdown", (event) => event.preventDefault());
        item.addEventListener("click", () => chooseTo(account.path));
        return item;
      }),
    );
    toOptions.hidden = matches.length === 0;
    toInput.setAttribute("aria-expanded", String(matches.length > 0));
    activeOption = -1;
  };

  toInput.addEventListener("focus", () => {
    // Selecting the current account lets the first keystroke replace it.
    if (selectedTo()) toInput.select();
    openOptions();
  });
  toInput.addEventListener("input", () => {
    openOptions();
    accountsChanged();
  });
  toInput.addEventListener("blur", closeOptions);
  toInput.addEventListener("keydown", (event) => {
    const count = toOptions.querySelectorAll("li").length;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (toOptions.hidden) openOptions();
      highlight(Math.min(activeOption + 1, count - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      highlight(Math.max(activeOption - 1, 0));
    } else if (event.key === "Enter" && !toOptions.hidden && activeOption >= 0) {
      event.preventDefault();
      chooseTo(matchingAccounts()[activeOption].path);
    } else if (event.key === "Escape") {
      closeOptions();
    }
  });

  // --- Conversion ----------------------------------------------------------

  const describeRate = (data) => {
    if (!data.source) return "No rate found. Enter the amount.";
    const note = `${data.source}, ${data.rate_date}`;
    return data.to_amount === null ? `${note}. The amount is too small to convert.` : note;
  };

  const requestRate = async () => {
    const amount = cleanAmount(amountInput.value);
    if (!needsConversion() || amount === "" || dateInput.value === "") return;
    const request = ++rateRequest;
    rateNote.textContent = "Looking up the rate…";
    const result = await post("/api/rate", {
      from: fromSelect.value,
      to: toInput.value,
      date: dateInput.value,
      amount,
    }).catch(() => null);
    if (request !== rateRequest) return;
    if (result === null || result.status !== 200) {
      toAmountInput.value = "";
      if (result && result.status === 401) {
        rateNote.textContent = "Wrong username or password.";
      } else if (result && result.status === 400) {
        rateNote.textContent = result.data.error;
      } else {
        rateNote.textContent = "No rate found. Enter the amount.";
      }
      updateAddButton();
      return;
    }
    toAmountInput.value = result.data.to_amount ?? "";
    rateNote.textContent = describeRate(result.data);
    updateAddButton();
  };

  // The converted amount belongs to the inputs it was computed from, so any
  // change clears it, which keeps Add disabled until the new one arrives.
  const scheduleRate = () => {
    clearTimeout(rateTimer);
    rateRequest += 1;
    toAmountInput.value = "";
    rateNote.textContent = "Looking up the rate…";
    updateAddButton();
    rateTimer = setTimeout(requestRate, 300);
  };

  function accountsChanged() {
    const from = selectedFrom();
    amountCurrency.textContent = from ? from.currency : "";
    const convert = needsConversion();
    conversion.hidden = !convert;
    if (convert) {
      toCurrency.textContent = selectedTo().currency;
      scheduleRate();
    } else {
      toAmountInput.value = "";
      rateNote.textContent = "";
    }
    updateAddButton();
  }

  amountInput.addEventListener("input", () => {
    updateAddButton();
    if (needsConversion()) scheduleRate();
  });
  dateInput.addEventListener("change", () => {
    updateAddButton();
    if (needsConversion()) scheduleRate();
  });
  fromSelect.addEventListener("change", accountsChanged);
  toAmountInput.addEventListener("input", updateAddButton);

  // --- Signing in and adding -----------------------------------------------

  const resetToSignedOut = () => {
    clearTimeout(rateTimer);
    rateRequest += 1;
    credentials = null;
    passwordInput.value = "";
    amountInput.value = "";
    descriptionInput.value = "";
    toAmountInput.value = "";
    rateNote.textContent = "";
    fields.disabled = true;
    signInButton.disabled = false;
    signInForm.hidden = false;
    updateAddButton();
  };

  signInForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    signInButton.disabled = true;
    showStatus("Signing in…");
    credentials = { username: usernameInput.value, password: passwordInput.value };
    const result = await post("/api/accounts", {}).catch(() => null);
    if (result === null || result.status !== 200) {
      credentials = null;
      signInButton.disabled = false;
      showStatus(
        result && result.status === 401
          ? "Wrong username or password."
          : "Could not sign in. Try again.",
        "error",
      );
      return;
    }
    fromAccounts = result.data.from;
    toAccounts = result.data.to;
    fromSelect.replaceChildren(
      ...fromAccounts.map((account) => new Option(account.path, account.path)),
    );
    fromSelect.value = result.data.from_default ?? "";
    toInput.value = result.data.to_default ?? "";
    dateInput.value = today();
    fields.disabled = false;
    signInForm.hidden = true;
    showStatus("");
    accountsChanged();
    amountInput.focus();
  });

  // Enabled only once this script runs, so the form cannot be submitted
  // natively before its submit handler exists.
  signInButton.disabled = false;

  expenseForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (addButton.disabled) return;
    addButton.disabled = true;
    showStatus("Adding…");
    const result = await post("/api/expenses", {
      from: fromSelect.value,
      to: toInput.value,
      date: dateInput.value,
      description: descriptionInput.value,
      amount: cleanAmount(amountInput.value),
      to_amount: needsConversion() ? cleanAmount(toAmountInput.value) : "",
    }).catch(() => null);
    if (result === null || result.status !== 200) {
      if (result && result.status === 401) resetToSignedOut();
      showStatus(result ? errorMessage(result) : "Could not add the expense. Try again.", "error");
      updateAddButton();
      return;
    }
    const added = result.data;
    showStatus(
      `Added: ${added.date}, ${added.amount} ${added.currency}, ${added.from} → ${added.to}`,
      "added",
    );
    resetToSignedOut();
    passwordInput.focus();
  });
})();
