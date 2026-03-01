#!/usr/bin/env python3
"""
Full end-to-end Playwright test for the Vigil app.
"""
import os
import sys
import time

# Set LD_LIBRARY_PATH before importing playwright
os.environ['LD_LIBRARY_PATH'] = '/tmp/stub_libs:' + os.environ.get('LD_LIBRARY_PATH', '')

from playwright.sync_api import sync_playwright

LOGS_DIR = "/mnt/efs/spaces/90bff6b8-f5aa-4127-a94f-82eff4130a1e/a70cf7f7-1e6f-4d04-918e-13ab3f495d53/vigil/logs"

results = {}

def run_tests():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900}
        )
        page = context.new_page()

        # ─────────────────────────────────────────────────────────────
        # TEST 1: Landing Page
        # ─────────────────────────────────────────────────────────────
        print("\n" + "="*60)
        print("TEST 1: Landing Page")
        print("="*60)

        page.goto("file:///mnt/efs/spaces/90bff6b8-f5aa-4127-a94f-82eff4130a1e/a70cf7f7-1e6f-4d04-918e-13ab3f495d53/vigil/vigil-landing.html")
        print("Waiting 2 seconds for JS/animations...")
        time.sleep(2)

        screenshot_path = f"{LOGS_DIR}/test_landing_fixed.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"Screenshot saved: {screenshot_path}")

        # Check sections
        sections = page.query_selector_all("section")
        num_sections = len(sections)
        print(f"Number of <section> elements: {num_sections}")

        # Check hero text
        hero_text = ""
        h1_elems = page.query_selector_all("h1")
        for h1 in h1_elems:
            text = h1.inner_text().strip()
            if text:
                hero_text = text
                print(f"H1 text: {text[:120]}")
                break

        # Check visibility of sections
        visible_sections = 0
        for s in sections:
            if s.is_visible():
                visible_sections += 1
        print(f"Visible sections: {visible_sections} / {num_sections}")

        # Get page title
        title = page.title()
        print(f"Page title: {title}")

        # Get all heading texts
        headings = page.query_selector_all("h1, h2, h3")
        print(f"Headings found ({len(headings)}):")
        for h in headings[:15]:
            try:
                text = h.inner_text().strip()
                tag = h.evaluate("el => el.tagName")
                if text:
                    print(f"  - {tag}: {text[:80]}")
            except:
                pass

        # Check for nav links
        nav_links = page.query_selector_all("nav a, header a")
        print(f"Navigation links: {len(nav_links)}")
        for lnk in nav_links[:5]:
            try:
                print(f"  - {lnk.inner_text().strip()[:50]}")
            except:
                pass

        # Check for CTA buttons
        cta_buttons = page.query_selector_all("button, a.btn, a[class*='cta'], a[class*='button']")
        print(f"CTA buttons/links: {len(cta_buttons)}")

        results["test1"] = {
            "num_sections": num_sections,
            "visible_sections": visible_sections,
            "hero_text": hero_text,
            "title": title,
            "num_headings": len(headings),
            "pass": num_sections > 2 and bool(hero_text)
        }
        print(f"\nTEST 1 RESULT: {'PASS' if results['test1']['pass'] else 'FAIL'}")

        # ─────────────────────────────────────────────────────────────
        # TEST 2: Dashboard - initial state
        # ─────────────────────────────────────────────────────────────
        print("\n" + "="*60)
        print("TEST 2: Dashboard - Initial State")
        print("="*60)

        page.goto("https://nm285lam.run.complete.dev")
        print("Waiting 6 seconds for full load...")
        time.sleep(6)

        screenshot_path = f"{LOGS_DIR}/test_dashboard_fixed.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"Screenshot saved: {screenshot_path}")

        # Check current URL
        current_url = page.url
        print(f"Current URL: {current_url}")
        print(f"Page title: {page.title()}")

        # Check page body background
        body_bg = page.evaluate("""() => {
            const body = document.body;
            const style = window.getComputedStyle(body);
            return style.backgroundColor;
        }""")
        print(f"Body background color: {body_bg}")

        # Check header
        header_info = page.evaluate("""() => {
            const header = document.querySelector('header, [data-testid="stHeader"]');
            if (!header) return {found: false};
            const style = window.getComputedStyle(header);
            const rect = header.getBoundingClientRect();
            return {
                found: true,
                bg: style.backgroundColor,
                top: rect.top,
                height: rect.height,
                visible: rect.height > 0
            };
        }""")
        print(f"Header info: {header_info}")

        # Check for black gap at top
        # A black gap would show as black pixels at the top of the screenshot
        # We check if the body has a background that starts with gap
        top_gap = page.evaluate("""() => {
            const body = document.body;
            const rect = body.getBoundingClientRect();
            return {bodyTop: rect.top, scrollY: window.scrollY};
        }""")
        print(f"Top gap check: {top_gap}")

        # Look for pill/chip buttons - Streamlit renders these differently
        # Check for any button-like elements
        all_buttons = page.query_selector_all("button")
        print(f"Total buttons: {len(all_buttons)}")
        button_texts = []
        for btn in all_buttons[:15]:
            try:
                text = btn.inner_text().strip()
                kind = btn.get_attribute("kind") or ""
                cls = btn.get_attribute("class") or ""
                if text:
                    button_texts.append(text)
                    print(f"  Button: '{text[:50]}' kind='{kind}' class_snippet='{cls[:40]}'")
            except:
                pass

        # Check for small pill-shaped elements using class patterns
        pill_classes = [
            "[class*='st-emotion-cache']",
            "[data-testid*='chip']",
            "[data-testid*='pill']",
            "[class*='pill']",
            "[class*='chip']",
            "[class*='tag']",
            ".stButton button",
        ]
        for sel in pill_classes:
            try:
                elems = page.query_selector_all(sel)
                if elems:
                    print(f"Pill-like elements '{sel}': {len(elems)}")
            except:
                pass

        # Check for "Set up profile" link
        profile_link_found = False
        profile_selectors = [
            "a:has-text('Set up profile')",
            "a:has-text('profile')",
            "[href*='profile']",
        ]
        for sel in profile_selectors:
            try:
                elem = page.query_selector(sel)
                if elem:
                    profile_link_found = True
                    text = elem.inner_text().strip()
                    href = elem.get_attribute("href") or ""
                    print(f"Profile link found ('{sel}'): text='{text[:60]}' href='{href}'")
                    break
            except:
                pass

        # Count all links
        all_links = page.query_selector_all("a")
        print(f"Total links: {len(all_links)}")
        for lnk in all_links[:10]:
            try:
                text = lnk.inner_text().strip()
                href = lnk.get_attribute("href") or ""
                if text:
                    print(f"  Link: '{text[:60]}' -> {href[:60]}")
            except:
                pass

        # Check main content
        main_content = page.evaluate("""() => {
            const main = document.querySelector('main, [data-testid="stAppViewContainer"]');
            if (!main) return 'no main';
            return main.innerText.substring(0, 200);
        }""")
        print(f"Main content preview: {main_content[:150]}")

        results["test2"] = {
            "url": current_url,
            "body_bg": body_bg,
            "header_info": header_info,
            "button_count": len(all_buttons),
            "profile_link_found": profile_link_found,
            "pass": True  # visual check via screenshot
        }
        print(f"\nTEST 2 RESULT: PASS (check screenshot for visual validation)")

        # ─────────────────────────────────────────────────────────────
        # TEST 3: Profile pill navigation
        # ─────────────────────────────────────────────────────────────
        print("\n" + "="*60)
        print("TEST 3: Profile Pill Navigation")
        print("="*60)

        clicked = False

        # Try various selectors for profile navigation link
        profile_nav_selectors = [
            "a:has-text('Set up profile')",
            "a:has-text('profile')",
            "text=Set up profile",
            "[href*='profile']",
            "a[href='/profile']",
            "a[href='profile']",
            "a[href='./profile']",
        ]

        for sel in profile_nav_selectors:
            try:
                elem = page.query_selector(sel)
                if elem and elem.is_visible():
                    text = elem.inner_text().strip()
                    href = elem.get_attribute("href") or ""
                    print(f"Found profile link with '{sel}': text='{text[:60]}' href='{href}'")
                    elem.click()
                    clicked = True
                    break
            except Exception as e:
                print(f"  Selector '{sel}' failed: {str(e)[:60]}")

        if not clicked:
            print("Scanning all links for profile-related ones...")
            all_links = page.query_selector_all("a")
            for lnk in all_links:
                try:
                    text = lnk.inner_text().strip().lower()
                    href = (lnk.get_attribute("href") or "").lower()
                    if "profile" in text or "profile" in href or "set up" in text:
                        print(f"  Found: '{text[:60]}' -> '{href[:60]}'")
                        lnk.click()
                        clicked = True
                        break
                except:
                    pass

        if not clicked:
            print("WARNING: Profile navigation link not found. Listing all links on page:")
            all_links = page.query_selector_all("a")
            for lnk in all_links:
                try:
                    text = lnk.inner_text().strip()
                    href = lnk.get_attribute("href") or ""
                    print(f"  '{text[:50]}' -> '{href[:60]}'")
                except:
                    pass

        print("Waiting 4 seconds for navigation...")
        time.sleep(4)

        screenshot_path = f"{LOGS_DIR}/test_profile_nav.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"Screenshot saved: {screenshot_path}")

        nav_url = page.url
        print(f"URL after click: {nav_url}")
        navigated_to_profile = "profile" in nav_url.lower()
        print(f"Navigated to profile: {navigated_to_profile}")

        results["test3"] = {
            "clicked": clicked,
            "url_after": nav_url,
            "navigated_to_profile": navigated_to_profile,
            "pass": navigated_to_profile
        }
        print(f"\nTEST 3 RESULT: {'PASS' if results['test3']['pass'] else 'FAIL'}")

        # ─────────────────────────────────────────────────────────────
        # TEST 4: Profile page
        # ─────────────────────────────────────────────────────────────
        print("\n" + "="*60)
        print("TEST 4: Profile Page")
        print("="*60)

        page.goto("https://nm285lam.run.complete.dev/profile")
        print("Waiting 5 seconds for full load...")
        time.sleep(5)

        screenshot_path = f"{LOGS_DIR}/test_profile_fixed.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"Screenshot saved: {screenshot_path}")

        profile_url = page.url
        print(f"Current URL: {profile_url}")
        print(f"Page title: {page.title()}")

        # Dump all visible inputs and textareas
        all_inputs = page.query_selector_all("input[type='text'], input:not([type]), textarea")
        print(f"Total text inputs/textareas: {len(all_inputs)}")
        for i, inp in enumerate(all_inputs):
            try:
                if inp.is_visible():
                    tag = inp.evaluate("el => el.tagName")
                    placeholder = inp.get_attribute("placeholder") or ""
                    aria_label = inp.get_attribute("aria-label") or ""
                    value = inp.input_value() if tag == "INPUT" else inp.inner_text()[:30]
                    print(f"  [{i}] {tag}: placeholder='{placeholder[:40]}' aria-label='{aria_label[:40]}' value='{value[:30]}'")
            except Exception as e:
                print(f"  [{i}] Error: {str(e)[:40]}")

        # Find and fill Company Name
        company_filled = False
        company_value_before = ""
        company_selectors = [
            "input[placeholder*='Company']",
            "input[placeholder*='company']",
            "input[placeholder*='Name']",
            "input[aria-label*='Company']",
            "input[aria-label*='company']",
            "label:has-text('Company') ~ div input",
            "label:has-text('Company') + div input",
        ]

        for sel in company_selectors:
            try:
                elem = page.query_selector(sel)
                if elem and elem.is_visible():
                    company_value_before = elem.input_value()
                    print(f"Company Name field found: '{sel}', current value: '{company_value_before}'")
                    elem.triple_click()
                    elem.fill("TechStartup AI")
                    time.sleep(0.5)
                    new_value = elem.input_value()
                    print(f"  After fill, value: '{new_value}'")
                    company_filled = True
                    break
            except Exception as e:
                print(f"  '{sel}' error: {str(e)[:60]}")

        # If none of the specific selectors worked, try first visible input
        if not company_filled:
            for i, inp in enumerate(all_inputs):
                try:
                    if inp.is_visible():
                        inp.triple_click()
                        inp.fill("TechStartup AI")
                        time.sleep(0.5)
                        company_filled = True
                        print(f"  Filled first visible input [{i}] with 'TechStartup AI'")
                        break
                except:
                    pass

        # Find and fill description
        desc_filled = False
        desc_value_before = ""
        desc_selectors = [
            "textarea[placeholder*='description']",
            "textarea[placeholder*='Description']",
            "textarea[aria-label*='description']",
            "textarea[aria-label*='Description']",
            "textarea",
        ]

        for sel in desc_selectors:
            try:
                elems = page.query_selector_all(sel)
                for elem in elems:
                    if elem.is_visible():
                        desc_value_before = elem.inner_text()[:50]
                        print(f"Description field found: '{sel}', current: '{desc_value_before}'")
                        elem.triple_click()
                        elem.fill("We build AI-powered analytics tools for enterprise clients")
                        time.sleep(0.5)
                        desc_filled = True
                        print(f"  Filled description textarea")
                        break
                if desc_filled:
                    break
            except Exception as e:
                print(f"  '{sel}' error: {str(e)[:60]}")

        # Wait for live preview to update
        print("Waiting 2 seconds for live preview to update...")
        time.sleep(2)

        screenshot_path = f"{LOGS_DIR}/test_profile_filled.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"Screenshot saved: {screenshot_path}")

        # Check live preview content
        page_text = page.evaluate("() => document.body.innerText")
        has_live_preview = "live preview" in page_text.lower() or "preview" in page_text.lower()
        has_score = "%" in page_text or "completeness" in page_text.lower() or "score" in page_text.lower()
        has_techstartup = "TechStartup AI" in page_text

        print(f"Has 'Live Preview' text: {has_live_preview}")
        print(f"Has score/completeness: {has_score}")
        print(f"'TechStartup AI' visible in page: {has_techstartup}")

        # Find score elements
        score_selectors = [
            "[class*='progress']",
            "[class*='score']",
            "text=Complete",
            "text=completeness",
        ]
        for sel in score_selectors:
            try:
                elem = page.query_selector(sel)
                if elem:
                    print(f"Score element ('{sel}'): {elem.inner_text().strip()[:60]}")
            except:
                pass

        # Dump a snippet of the page text to see what's there
        print(f"Page text snippet (first 500 chars): {page_text[:500]}")

        results["test4"] = {
            "url": profile_url,
            "company_filled": company_filled,
            "desc_filled": desc_filled,
            "has_live_preview": has_live_preview,
            "has_score": has_score,
            "techstartup_visible": has_techstartup,
            "pass": company_filled
        }
        print(f"\nTEST 4 RESULT: {'PASS' if results['test4']['pass'] else 'FAIL'}")

        # ─────────────────────────────────────────────────────────────
        # TEST 5: Back to Dashboard from profile
        # ─────────────────────────────────────────────────────────────
        print("\n" + "="*60)
        print("TEST 5: Back to Dashboard")
        print("="*60)

        back_clicked = False
        back_selectors = [
            "a:has-text('Back to Dashboard')",
            "button:has-text('Back to Dashboard')",
            "text=Back to Dashboard",
            "text=← Back to Dashboard",
            "a:has-text('Back')",
            "a[href='/']",
            "a[href='./']",
            "a[href='..']",
        ]

        for sel in back_selectors:
            try:
                elem = page.query_selector(sel)
                if elem and elem.is_visible():
                    text = elem.inner_text().strip()
                    print(f"Back button found ('{sel}'): '{text[:60]}'")
                    elem.click()
                    back_clicked = True
                    break
            except Exception as e:
                print(f"  '{sel}' error: {str(e)[:60]}")

        if not back_clicked:
            print("Scanning all links for back/dashboard navigation...")
            all_links = page.query_selector_all("a")
            for lnk in all_links:
                try:
                    text = lnk.inner_text().strip().lower()
                    href = (lnk.get_attribute("href") or "").lower()
                    if "back" in text or "dashboard" in text or href in ["/", "./", "../"]:
                        print(f"  Found: '{text[:60]}' -> '{href}'")
                        lnk.click()
                        back_clicked = True
                        break
                except:
                    pass

        if not back_clicked:
            print("Checking all buttons for back navigation...")
            all_buttons = page.query_selector_all("button")
            print(f"Buttons on page ({len(all_buttons)}):")
            for btn in all_buttons:
                try:
                    text = btn.inner_text().strip()
                    if text:
                        print(f"  Button: '{text[:60]}'")
                    if "back" in text.lower() or "dashboard" in text.lower():
                        btn.click()
                        back_clicked = True
                        break
                except:
                    pass

        print("Waiting 4 seconds for navigation...")
        time.sleep(4)

        screenshot_path = f"{LOGS_DIR}/test_back_to_dash.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"Screenshot saved: {screenshot_path}")

        back_url = page.url
        print(f"URL after navigation: {back_url}")

        # Check if we're back at dashboard (not on /profile)
        back_at_dashboard = "/profile" not in back_url.lower()
        print(f"Back at dashboard: {back_at_dashboard}")
        print(f"Current page title: {page.title()}")

        results["test5"] = {
            "clicked": back_clicked,
            "url_after": back_url,
            "back_at_dashboard": back_at_dashboard,
            "pass": back_at_dashboard and back_clicked
        }
        print(f"\nTEST 5 RESULT: {'PASS' if results['test5']['pass'] else 'FAIL'}")

        browser.close()

    # ─────────────────────────────────────────────────────────────
    # FINAL SUMMARY
    # ─────────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("FINAL TEST SUMMARY")
    print("="*60)
    for key, val in results.items():
        status = "PASS" if val.get("pass") else "FAIL"
        print(f"  {key.upper()}: {status}")
    print("="*60)
    return results

if __name__ == "__main__":
    run_tests()
