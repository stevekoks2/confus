from datetime import datetime
from . import db

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Уникальный индекс для предотвращения дублирования лайков
    __table_args__ = (
        db.UniqueConstraint('user_id', 'post_id', name='unique_like'),
    )

    def __repr__(self):
        return f"Like(user_id={self.user_id}, post_id={self.post_id})"