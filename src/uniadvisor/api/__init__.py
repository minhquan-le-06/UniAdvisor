"""The web API: the same planner and texts as the Streamlit app, as JSON, with no session on the server.

The browser keeps the student's plan (the plan file, ui/plan_file.py) and sends it with every request; the server
checks it, computes, answers, and keeps and logs nothing. It never imports Streamlit or the local language model.
"""
