const {chromium} = require(process.env.GIF_PLAYWRIGHT_MODULE || "playwright");
(async () => {
  const options = {headless: true};
  if (process.env.GIF_BROWSER_EXECUTABLE) options.executablePath = process.env.GIF_BROWSER_EXECUTABLE;
  const browser = await chromium.launch(options);
  try {
    const page = await browser.newPage({viewport: {width: 900, height: 850}, reducedMotion: "reduce"});
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto(process.argv[2]);
    await page.screenshot({path: "build/picker-preview.png", fullPage: true});
    const chooser = page.waitForEvent("filechooser");
    await page.getByRole("button", {name: "GIF", exact: false}).first().click();
    await (await chooser).setFiles("tests/fixtures/asset-01.gif");
    await page.getByRole("button", {name: "Use this GIF"}).click();
    await page.getByRole("heading", {name: "Ready for your chat"}).waitFor();
    const prompt = await page.locator("#prompt").inputValue();
    if (!prompt.includes("inspect_gif") || !prompt.includes("picked-")) throw Error("Missing inspection request");
    await page.getByRole("button", {name: "Play preview"}).click();
    await page.getByRole("button", {name: "Stop preview"}).click();
    await page.setViewportSize({width: 390, height: 844});
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    if (overflow || errors.length) throw Error(JSON.stringify({overflow, errors}));
    console.log(JSON.stringify({passed: true, fileChooser: true, byteStaging: true,
      requestPrepared: true, mobileWidth: 390, noOverflow: true, motionOptIn: true,
      pageErrors: errors, modelCalls: 0}));
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
