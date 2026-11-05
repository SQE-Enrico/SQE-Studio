"""Real Chromium drives the saved native-source to scqubits research workflow."""
import json
from pathlib import Path
import shutil
import time

from .process_temp import process_workspace


class NativeBrowserUnavailable(RuntimeError):
    pass


def run_browser_chain(session, source_root, folder):
    from playwright.sync_api import sync_playwright, expect, Error as PlaywrightError
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    errors = []
    with process_workspace(source_root) as private, sync_playwright() as playwright:
        executable = next((shutil.which(name) for name in
            ('chromium', 'chromium-browser', 'google-chrome', 'msedge', 'chrome')
            if shutil.which(name)), None)
        options = {'headless': True, 'args': ['--no-sandbox']}
        if executable:
            options['executable_path'] = executable
        try:
            browser = playwright.chromium.launch(**options)
        except PlaywrightError as error:
            if "executable doesn't exist" in str(error).lower():
                raise NativeBrowserUnavailable('PLAYWRIGHT_CHROMIUM_NOT_INSTALLED') from error
            raise
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(session.base, wait_until='networkidle', timeout=20000)
            page.locator('#email').fill(session.email)
            page.locator('#password').fill(session.password)
            page.locator('#authSubmit').click()
            expect(page.locator('#currentProjectName')).to_have_text('Native single transmon reference')
            page.locator('#stages [data-step="3"]').click()
            expect(page.locator('#transmonState')).to_contain_text('READY_TO_SAVE')
            expect(page.locator('#transmonIslandA')).to_have_value('Q1_pad_bot')
            expect(page.locator('#transmonIslandB')).to_have_value('Q1_pad_top')
            # Ordinary GUI edits must retain native reference-group identities.
            page.locator('#saveEMSettings').click()
            page.locator('#saveButton').click()
            expect(page.locator('#transmonState')).to_contain_text('READY_TO_SAVE')
            with page.expect_response(lambda response: response.url.endswith('/runs')
                    and response.request.method == 'POST', timeout=20000) as requested:
                page.locator('#runEM').click()
            queued = requested.value
            if queued.status != 202:
                raise ValueError('BROWSER_NATIVE_EM_REQUEST_FAILED')
            source_run = queued.json()['run_id']
            capacitance = session.wait(source_run, time.monotonic() + 1000)
            if capacitance['manifest']['artifact_type'] != 'palace.capacitance_matrix':
                raise ValueError('BROWSER_CAPACITANCE_RESULT_REQUIRED')
            page.locator('#refreshJobs').click()
            source_button = page.locator(f'[data-get-result="{source_run}"]')
            expect(source_button).to_have_text('Inspect verified source', timeout=20000)
            source_button.click()
            page.locator('#extractionCj').wait_for(timeout=20000)
            page.locator('#extractionCj').fill('12')
            page.locator('#extractionCjRef').fill('Browser reference assumption: additional C_J=12 fF, unmeasured.')
            page.locator('#extractionJType').select_option('LJ')
            page.locator('#extractionJValue').fill('10.897434187118746')
            page.locator('#extractionJRef').fill('Browser reference assumption: L_J=10.897434187118746 nH, unmeasured.')
            page.locator('#extractionAck').check()
            endpoint = f'/runs/{source_run}/extraction'
            with page.expect_response(lambda response: response.url.endswith(endpoint)
                    and response.request.method == 'POST', timeout=25000) as requested:
                page.locator('#extractionPreview').click()
            preview_response = requested.value
            if preview_response.status != 200:
                raise ValueError('BROWSER_EXTRACTION_PREVIEW_FAILED: ' + preview_response.text()[:1500])
            preview = preview_response.json()
            if preview['extraction']['source']['run_id'] != source_run:
                raise ValueError('BROWSER_PREVIEW_SOURCE_CHANGED')
            expect(page.locator('#extractionExecute')).to_be_enabled()
            with page.expect_response(lambda response: response.url.endswith(endpoint)
                    and response.request.method == 'POST', timeout=25000) as requested:
                page.locator('#extractionExecute').click()
            executed = requested.value
            if executed.status != 202 or not executed.json().get('run_id'):
                raise ValueError('BROWSER_QUANTIZATION_NOT_QUEUED')
            quantum_run = executed.json()['run_id']
            result = session.wait(quantum_run, time.monotonic() + 200)
            page.locator('#refreshJobs').click()
            result_button = page.locator(f'[data-get-result="{quantum_run}"]')
            expect(result_button).to_have_text('Inspect verified source', timeout=20000)
            result_button.click()
            expect(page.locator('#resultView')).to_contain_text('Extraction → conditional quantization')
            expect(page.locator('#resultView')).to_contain_text('NUMERICAL_PASS')
            expect(page.locator('#resultView')).to_contain_text(source_run)
            if errors:
                raise ValueError('BROWSER_JAVASCRIPT_ERRORS: ' + str(errors)[:1500])
            page.screenshot(path=str(private / 'single-transmon.png'), full_page=True)
            shutil.copyfile(private / 'single-transmon.png', folder / 'single-transmon.png')
            (folder / 'browser-quantum-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            spectrum, extraction = result['spectrum'], result['conditional_extraction']
            if (extraction['source']['run_id'] != source_run
                    or extraction['extraction_sha256'] != preview['extraction']['extraction_sha256']
                    or spectrum['extraction_sha256'] != extraction['extraction_sha256']
                    or result['manifest']['revision_id'] != executed.json()['revision']
                    or abs(extraction['parameters']['EJ'] - 15.) > 1e-10
                    or abs(extraction['capacitances']['additional_junction_F'] - 12e-15) > 1e-27
                    or spectrum['convergence']['numeric_status'] != 'NUMERICAL_PASS'):
                raise ValueError('BROWSER_NATIVE_LINEAGE_OR_BASIS_FAILED')
            levels = spectrum['levels']
            return {'status': 'PASS', 'execution_kind': 'REAL_CHROMIUM_NATIVE_HTTP_WORKFLOW',
                'source_run_id': source_run, 'quantum_run_id': quantum_run,
                'parameters': extraction['parameters'], 'capacitances': extraction['capacitances'],
                'f01_GHz': levels[1]-levels[0],
                'anharmonicity_GHz': levels[2]-2*levels[1]+levels[0],
                'basis_convergence': spectrum['convergence'], 'screenshot': 'single-transmon.png',
                'scientific_qualification': 'NOT_ESTABLISHED', 'fabrication': 'HOLD'}
        finally:
            browser.close()
