# Add these to your existing *exclusions* regex for the relevant scenario (functional/security)
NOISSUE_EXCLUSIONS_STRONGER = r"\b(except|but|however|though|nevertheless|yet|still|apart\s+from|except\s+for|"
NOISSUE_EXCLUSIONS_STRONGER += r"potential|risk|could|might|may|possibly|possible|caveat|concern|limitation|improvement)\b"

NOISSUE_CONFIG_FUNC["exclusions"] = NOISSUE_EXCLUSIONS_STRONGER
# (Do the same for your security no-issue config if needed.)
