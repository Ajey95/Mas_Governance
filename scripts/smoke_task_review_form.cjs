/* Browser smoke test for the generated, fully offline reviewer form. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { chromium } = require("../frontend/node_modules/playwright");

async function main() {
  const htmlPath = path.resolve(process.argv[2] || "datasets/task_review_packet_v3/offline_review_form.html");
  const html = fs.readFileSync(htmlPath, "utf8");
  const payload = JSON.parse(html.match(/const REVIEW_DATA = (.+);\r?\n/)[1]);
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "mas-review-smoke-"));
  const browser = await chromium.launch({ headless: true, channel: "chrome" });
  try {
    const context = await browser.newContext({ acceptDownloads: true });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(pathToFileURL(htmlPath).href);
    assert.equal(await page.locator(".case-link").count(), 35);
    assert.equal(await page.locator("#caseId").textContent(), "cf_deploy_config_01");
    assert.equal(await page.locator("#provenanceFlag").isVisible(), true);
    await page.locator("#reviewerId").fill("smoke_test_only");
    await page.locator("#reviewerRole").fill("test automation");
    await page.locator('input[name="decision"][value="reject"]').check();
    await page.locator("#rationale").fill("Test-only rationale; this is not a human review.");
    const progressPromise = page.waitForEvent("download");
    await page.locator("#saveDraft").click();
    const progress = await progressPromise;
    const progressPath = path.join(temp, "progress.json");
    await progress.saveAs(progressPath);
    const saved = JSON.parse(fs.readFileSync(progressPath, "utf8"));
    assert.equal(saved.answers.cf_deploy_config_01.decision, "reject");
    assert.match(saved.answers.cf_deploy_config_01.recorded_at, /\+00:00$/);

    await page.reload();
    assert.equal(await page.locator("#reviewerId").inputValue(), "");
    await page.locator("#loadDraft").setInputFiles(progressPath);
    assert.equal(await page.locator("#reviewerId").inputValue(), "smoke_test_only");
    assert.equal(await page.locator("#caseId").textContent(), "cf_cleanup_script_02");
    await page.locator(".case-link").first().click();
    assert.equal(await page.locator("#rationale").inputValue(), saved.answers.cf_deploy_config_01.rationale);
    await page.locator("#exportFinal").click();
    assert.match(await page.locator("#message").textContent(), /34 task\(s\) need/);

    for (let index = 1; index < 35; index++) {
      if (index > 1) await page.locator("#next").click();
      await page.locator('input[name="decision"][value="approve"]').check();
      await page.locator("#rationale").fill("Test-only rationale; this is not a human review.");
    }
    const finalPromise = page.waitForEvent("download");
    await page.locator("#exportFinal").click();
    const final = await finalPromise;
    const finalPath = path.join(temp, "test-only.jsonl");
    await final.saveAs(finalPath);
    const rows = fs.readFileSync(finalPath, "utf8").trim().split("\n").map(JSON.parse);
    assert.equal(rows.length, 35);
    assert.equal(new Set(rows.map(row => row.scenario_id)).size, 35);
    assert.equal(rows[0].decision, "reject");
    assert(rows.every((row, index) => row.scenario_sha256 === payload.packet[index].scenario_sha256));
    assert(rows.every(row => row.scenario_sha256.length === 64 && row.recorded_at.endsWith("+00:00")));
    assert.deepEqual(errors, []);
    console.log("Offline form browser smoke test passed: save, resume, incomplete gate, 35-row JSONL export.");
  } finally {
    await browser.close();
    fs.rmSync(temp, { recursive: true, force: true });
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
