# utils.py

def node_text(node, source):

    return source[
        node.start_byte:
        node.end_byte
    ].decode(
        "utf-8",
        errors="ignore"
    )