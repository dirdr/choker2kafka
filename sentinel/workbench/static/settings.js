import { api, saveInvestigatorSettings } from "./api.js";

export function wireInvestigatorSettings(onSaved) {
  const byId = (id) => document.getElementById(id);
  const dialog = byId("investigator-settings-dialog");
  const form = byId("investigator-settings-form");
  const fields = byId("settings-fields");
  const model = byId("settings-model");
  const tokens = byId("settings-tokens");
  const save = byId("settings-save");
  const status = byId("settings-status");
  const error = byId("settings-error");
  let current;
  let csrf;
  let saving = false;

  byId("investigator-settings-button").addEventListener("click", async () => {
    if (dialog.open) return;
    fields.disabled = true;
    save.disabled = true;
    error.hidden = true;
    status.hidden = false;
    status.textContent = "Loading settings…";
    dialog.showModal();
    try {
      const result = await api("/workbench/investigator/settings");
      if (!dialog.open) return;
      current = result.settings;
      csrf = result.csrf_token;
      const models = [...result.models];
      if (!models.some((item) => item.id === current.model_id))
        models.unshift({ id: current.model_id, name: current.model_id });
      model.replaceChildren();
      for (const item of models) {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = item.name;
        model.append(option);
      }
      model.value = current.model_id;
      tokens.value = current.token_limit;
      byId("settings-model-hint").textContent = result.models.length
        ? "Models available to this application."
        : "Model list unavailable. Your current model is preserved.";
      fields.disabled = !result.editable;
      save.disabled = !result.editable;
      status.hidden = result.editable;
      if (!result.editable) status.textContent = "Settings changes are disabled on this deployment.";
      else model.focus();
    } catch (failure) {
      status.hidden = true;
      error.textContent = failure.message;
      error.hidden = false;
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (saving || !current || fields.disabled || !form.reportValidity()) return;
    saving = true;
    fields.disabled = true;
    save.disabled = true;
    save.textContent = "Saving…";
    error.hidden = true;
    try {
      await saveInvestigatorSettings({
        expected_revision: current.revision,
        model_id: model.value,
        token_limit: Number(tokens.value),
      }, csrf);
      dialog.close();
      await onSaved();
    } catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
    } finally {
      saving = false;
      fields.disabled = false;
      save.disabled = false;
      save.textContent = "Save settings";
    }
  });
}
