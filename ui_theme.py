"""Presentation helpers for the sunny, vintage legal-office theme."""
from pathlib import Path

import streamlit as st


def apply_theme():
    st.html(Path(__file__).with_name('theme.css'))


def masthead():
    st.html('''
    <div class="nl-masthead">
      <div class="nl-wordmark"><span class="nl-mark" aria-hidden="true">N.</span> NYAYA LENS</div>
      <span class="nl-edition">A LITTLE CLARITY. A LITTLE LESS WORRY.</span>
    </div>
    <section class="nl-hero" aria-label="Welcome to Nyaya Lens">
      <div class="nl-hero-copy">
        <span class="nl-eyebrow">YOUR STORY DESERVES TO BE HEARD</span>
        <h1>Let’s take it<br><em>one step at a time.</em></h1>
        <p>A calmer place to put the pieces together.<br>Tell us what happened, in your own words.</p>
        <div class="nl-hero-tags"><span>5 languages</span><span>Speak or type</span><span>At your pace</span></div>
      </div>
      <div class="nl-hero-art" aria-hidden="true">
        <div class="nl-sun"></div>
        <svg viewBox="0 0 300 245" class="nl-scales" fill="none">
          <path d="M149 37V202M92 207H210M112 194H190" stroke="#30291F" stroke-width="13" stroke-linecap="round"/>
          <path d="M57 83L243 61" stroke="#B83A28" stroke-width="12" stroke-linecap="round"/>
          <circle cx="149" cy="39" r="14" fill="#B83A28"/>
          <path d="M65 82L33 143M65 82L99 143M234 64L201 126M234 64L267 126" stroke="#30291F" stroke-width="4"/>
          <path d="M24 143H108C104 189 31 189 24 143Z" fill="#B83A28"/>
          <path d="M191 126H276C270 173 199 173 191 126Z" fill="#B83A28"/>
          <path d="M90 219H215" stroke="#30291F" stroke-width="5" stroke-linecap="round"/>
        </svg>
        <span class="nl-art-note">A fresh perspective.</span>
        <span class="nl-spark nl-spark-one">✦</span><span class="nl-spark nl-spark-two">✦</span>
      </div>
    </section>''')


def sidebar_brand():
    st.html('''<div class="nl-desk-brand"><span class="nl-eyebrow">THE CASE DESK</span>
    <h2>Good to have<br>you here.</h2><p>Get comfortable. We’ll keep things organized.</p></div>''')


def journey(active=1):
    steps = [(1, 'Your story'), (2, 'The details'), (3, 'Your case brief')]
    items = ''.join(
        f'<div class="nl-step {"is-active" if number == active else ""}"><span>0{number}</span>{label}</div>'
        for number, label in steps
    )
    st.html(f'<div class="nl-journey" aria-label="Intake stages">{items}</div>')


def conversation_heading(opening=False):
    title = 'Let’s get acquainted.' if opening else 'A little more of the story.'
    st.html(f'''<div class="nl-section-title"><span class="nl-eyebrow">THE CONVERSATION</span>
    <h2>{title}</h2><p>Listen, then answer however you feel comfortable.</p></div>''')
