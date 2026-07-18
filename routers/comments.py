"""Comments router."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth import CurrentUser
from database import get_db
import models  # type: ignore[reportMissingImports]
from schema import CommentCreate, CommentResponse, PaginatedCommentResponse

router = APIRouter()


@router.post("/{post_id}/comments", response_model=CommentResponse, status_code=status.HTTP_201_CREATED)
async def post_comment(
    post_id: int,
    comment_data: CommentCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    post_result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = post_result.scalars().first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    new_comment = models.CommentSection(
        user_id=current_user.id,
        post_id=post_id,
        content=comment_data.model_dump()["content"],
    )
    db.add(new_comment)
    await db.commit()
    await db.refresh(new_comment, attribute_names=["author"])
    return new_comment


@router.get("/{post_id}/comments", response_model=PaginatedCommentResponse)
async def get_comment(
    post_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    sort: Annotated[Literal["new", "old"], Query()] = "new",
):
    count_result = await db.execute(
        select(func.count()).select_from(models.CommentSection).where(models.CommentSection.post_id == post_id)
    )
    total = count_result.scalar() or 0

    order_by_clause = (
        models.CommentSection.date_posted.desc()
        if sort == "new"
        else models.CommentSection.date_posted.asc()
    )

    result = await db.execute(
        select(models.CommentSection)
        .options(selectinload(models.CommentSection.author))
        .where(models.CommentSection.post_id == post_id)
        .order_by(order_by_clause)
        .offset(skip)
        .limit(limit),
    )
    comments = result.scalars().all()

    has_more = skip + len(comments) < total

    return PaginatedCommentResponse(
        comments=[CommentResponse.model_validate(comment) for comment in comments],
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more,
    )
    
    
@router.put("/{post_id}", response_model=CommentResponse)
async def update_comment_full(
    post_id: int,
    current_user: CurrentUser,
    comment_data: CommentCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(models.CommentSection).where(models.CommentSection.post_id == post_id))
    comment = result.scalars().first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )
        
    if comment.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this comment",
        )
    
    comment.content = comment_data.content

    await db.commit()
    await db.refresh(comment, attribute_names=["author"])
    return comment


@router.patch("/{post_id}", response_model=CommentResponse)
async def update_post_partial(
    post_id: int,
    comment_data: CommentCreate,
    current_user:CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(models.Post).where(models.Post.id == post_id))
    post = result.scalars().first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post not found",
        )
        
    if post.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this post",
        )

    update_data = comment_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(post, field, value)

    await db.commit()
    await db.refresh(post, attribute_names=["author"])
    return post
