import random
from datetime import timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction
from faker import Faker

# Import all models
from apps.accounts.models import (
    Achievement,
    ActivityLog,
    Certification,
    Connection,
    Department,
    Education,
    Experience,
    Follow,
    Language,
    Message,
    Network,
    NetworkMembership,
)
from apps.accounts.models import Notification as AccountNotification
from apps.accounts.models import (
    ProfileStats,
    ProfileView,
    Project,
    ProjectImage,
    Publication,
    Recommendation,
    Resume,
    Role,
    SavedSearch,
    Skill,
    SkillEndorsement,
    SocialLink,
    Task,
    TaskComment,
    User,
    UserDepartment,
    UserFile,
    UserProfile,
    UserRole,
    Volunteer,
)
from apps.audit_log.models import AuditLog
from apps.blog.models import (
    BlogAnalytics,
    BlogAttachment,
    BlogBadge,
    BlogCategory,
    BlogComment,
    BlogModerationLog,
    BlogNewsletter,
    BlogPost,
    BlogPostVersion,
    BlogReaction,
    BlogReadingList,
    BlogSeries,
    BlogSeriesPost,
    BlogSubscription,
    BlogTag,
    BlogView,
    UserBlogBadge,
)
from apps.chats.models import (
    Chat,
    ChatAttachment,
    ChatBot,
    ChatCall,
    ChatCallParticipant,
    ChatFolder,
    ChatInviteLink,
    ChatJoinRequest,
    ChatMessage,
    ChatModerationLog,
    ChatParticipant,
    ChatPoll,
    ChatPollAnswer,
    ChatPollOption,
    ChatSticker,
    ChatStickerSet,
    ChatTheme,
    ChatWebhook,
    UserStickerSet,
)
from apps.common.models import Action, Comment, React, Tag, View
from apps.events.models import (
    Event,
    EventAnalytics,
    EventAttachment,
    EventBadge,
    EventCategory,
    EventCategoryRelation,
    EventFavorite,
    EventModerationLog,
    EventTag,
    EventTagRelation,
    EventView,
    Exhibitor,
    Participant,
    ParticipantBadge,
    Product,
    Session,
    SessionRating,
)
from apps.feedback.models import Feedback
from apps.notifications.models import (
    Notification,
    NotificationBatch,
    NotificationTemplate,
)
from apps.payment.models import Payment, PaymentGatewayConfig, Refund, Transaction

fake = Faker()
User = get_user_model()


class Command(BaseCommand):
    help = "Populate database with comprehensive test data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--users", type=int, default=200, help="Number of users to create"
        )
        parser.add_argument(
            "--clear", action="store_true", help="Clear existing data before populating"
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write("Clearing existing data...")
            self.clear_data()

        self.stdout.write("Starting data population...")

        with transaction.atomic():
            # Create data in dependency order
            self.create_base_data(options["users"])
            self.create_account_data()
            self.create_common_data()
            self.create_blog_data()
            self.create_event_data()
            self.create_chat_data()
            self.create_payment_data()
            self.create_notification_data()
            self.create_feedback_data()
            self.create_audit_data()

        self.stdout.write(
            self.style.SUCCESS("Successfully populated database with test data")
        )

    def clear_data(self):
        """Clear all existing data"""
        models_to_clear = [
            # Clear in reverse dependency order
            AuditLog,
            Feedback,
            Notification,
            Transaction,
            Refund,
            Payment,
            PaymentGatewayConfig,
            ChatWebhook,
            ChatJoinRequest,
            ChatInviteLink,
            ChatModerationLog,
            ChatTheme,
            UserStickerSet,
            ChatSticker,
            ChatStickerSet,
            ChatPollAnswer,
            ChatPollOption,
            ChatPoll,
            ChatCallParticipant,
            ChatCall,
            ChatBot,
            ChatFolder,
            ChatAttachment,
            ChatMessage,
            ChatParticipant,
            Chat,
            EventModerationLog,
            EventView,
            EventFavorite,
            SessionRating,
            EventAttachment,
            ParticipantBadge,
            EventBadge,
            EventAnalytics,
            Product,
            Exhibitor,
            Participant,
            Session,
            EventTagRelation,
            EventCategoryRelation,
            EventTag,
            EventCategory,
            Event,
            BlogReadingList,
            BlogModerationLog,
            UserBlogBadge,
            BlogBadge,
            BlogNewsletter,
            BlogSeriesPost,
            BlogSeries,
            BlogAnalytics,
            BlogSubscription,
            BlogView,
            BlogReaction,
            BlogComment,
            BlogAttachment,
            BlogPostVersion,
            BlogPost,
            BlogTag,
            BlogCategory,
            Comment,
            View,
            React,
            Action,
            Tag,
            ProfileStats,
            SavedSearch,
            AccountNotification,
            Message,
            Recommendation,
            NetworkMembership,
            Network,
            Resume,
            TaskComment,
            Task,
            UserDepartment,
            Department,
            UserRole,
            Role,
            ActivityLog,
            UserFile,
            ProfileView,
            Follow,
            Connection,
            Volunteer,
            Publication,
            Achievement,
            Language,
            SkillEndorsement,
            Skill,
            ProjectImage,
            Project,
            Certification,
            Education,
            Experience,
            SocialLink,
            UserProfile,
            User,
        ]

        for model in models_to_clear:
            try:
                model.objects.all().delete()
            except Exception as e:
                self.stdout.write(f"Error clearing {model.__name__}: {e}")

    def create_base_data(self, num_users):
        """Create base users and roles"""
        self.stdout.write("Creating base data...")

        # Create roles
        roles = ["Admin", "Manager", "Editor", "Moderator", "User", "Viewer"]
        self.roles = []
        for role_name in roles:
            role = Role.objects.create(
                name=role_name,
                description=f"{role_name} role with specific permissions",
            )
            self.roles.append(role)

        # Create departments
        departments = [
            "Engineering",
            "Marketing",
            "Sales",
            "HR",
            "Finance",
            "Operations",
        ]
        self.departments = []
        for dept_name in departments:
            dept = Department.objects.create(
                name=dept_name,
                description=f"{dept_name} department",
            )
            self.departments.append(dept)

        # Create superuser
        admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin123",
            first_name="Admin",
            last_name="User",
        )

        # Create regular users
        self.users = [admin_user]
        for i in range(num_users - 1):
            user = User.objects.create_user(
                username=fake.user_name(),
                email=fake.unique.email(),
                password="password123",
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                is_active=random.choice([True, True, True, False]),  # 75% active
                status=random.choice([choice[0] for choice in User.UserStatus.choices]),
            )
            self.users.append(user)

        # Assign roles and departments to users
        for user in self.users:
            # Assign role
            UserRole.objects.create(
                user=user,
                role=random.choice(self.roles),
                assigned_at=fake.date_time_between(
                    start_date="-2y", end_date="now", tzinfo=dt_timezone.utc
                ),
            )

            # Assign department
            UserDepartment.objects.create(
                user=user,
                department=random.choice(self.departments),
                position=fake.job(),
                joined_at=fake.date_time_between(
                    start_date="-2y", end_date="now", tzinfo=dt_timezone.utc
                ),
            )

    def create_account_data(self):
        """Create account-related data"""
        self.stdout.write("Creating account data...")

        # Update user profiles (they are created automatically by signals)
        for user in self.users:
            if hasattr(user, "profile"):
                profile = user.profile
                profile.bio = fake.text(max_nb_chars=500)
                profile.date_of_birth = fake.date_of_birth(
                    minimum_age=18, maximum_age=80
                )
                profile.phone = fake.phone_number()
                profile.website = fake.url()
                profile.location = fake.city()
                profile.current_position = fake.job()
                profile.industry = fake.company()
                profile.visibility = random.choice(
                    [choice[0] for choice in UserProfile.ProfileVisibility.choices]
                )
                profile.email_notifications = {
                    "new_messages": fake.boolean(),
                    "updates": fake.boolean(),
                }
                profile.push_notifications = {
                    "new_messages": fake.boolean(),
                    "updates": fake.boolean(),
                }
                profile.show_email = fake.boolean(chance_of_getting_true=70)
                profile.show_phone = fake.boolean(chance_of_getting_true=70)
                profile.interests = fake.words(nb=5)
                profile.save()

        # Create social links
        platforms = [choice[0] for choice in SocialLink.Platform.choices]
        for user in random.sample(self.users, min(100, len(self.users))):
            for _ in range(random.randint(1, 3)):
                SocialLink.objects.create(
                    user=user,
                    platform=random.choice(platforms),
                    url=fake.url(),
                    is_visible=fake.boolean(),
                )

        # Create experiences
        for user in random.sample(self.users, min(150, len(self.users))):
            for _ in range(random.randint(1, 4)):
                start_date = fake.date_between(start_date="-10y", end_date="-1y")
                end_date = (
                    fake.date_between(start_date=start_date, end_date="today")
                    if fake.boolean()
                    else None
                )

                Experience.objects.create(
                    user=user,
                    title=fake.job(),
                    company=fake.company(),
                    location=fake.city(),
                    description=fake.text(max_nb_chars=500),
                    start_date=start_date,
                    end_date=end_date,
                    type=random.choice(
                        [choice[0] for choice in Experience.ExperienceType.choices]
                    ),
                    is_current=end_date is None,
                )

        # Create education
        for user in random.sample(self.users, min(120, len(self.users))):
            for _ in range(random.randint(1, 3)):
                start_date = fake.date_between(start_date="-15y", end_date="-5y")
                end_date = fake.date_between(start_date=start_date, end_date="today")

                Education.objects.create(
                    user=user,
                    institution=fake.company() + " University",
                    degree=random.choice(["Bachelor", "Master", "PhD", "Certificate"]),
                    field_of_study=fake.job(),
                    start_date=start_date,
                    end_date=end_date,
                    gpa=f"{random.randint(70, 100)}%",
                    description=fake.text(max_nb_chars=300),
                )

        # Create certifications
        for user in random.sample(self.users, min(100, len(self.users))):
            for _ in range(random.randint(1, 5)):
                issue_date = fake.date_between(start_date="-5y", end_date="today")
                expiry_date = (
                    fake.date_between(start_date=issue_date, end_date="+5y")
                    if fake.boolean()
                    else None
                )

                Certification.objects.create(
                    user=user,
                    name=fake.catch_phrase(),
                    issuer=fake.company(),
                    issue_date=issue_date,
                    expiration_date=expiry_date,
                    credential_id=fake.uuid4(),
                    credential_url=fake.url(),
                )

        # Create projects
        self.projects = []
        for user in random.sample(self.users, min(80, len(self.users))):
            for _ in range(random.randint(1, 3)):
                project = Project.objects.create(
                    user=user,
                    title=fake.catch_phrase(),
                    description=fake.text(max_nb_chars=1000),
                    url=fake.url(),
                    github_url=fake.url(),
                    start_date=fake.date_between(start_date="-3y", end_date="-1y"),
                    end_date=(
                        fake.date_between(start_date="-1y", end_date="today")
                        if fake.boolean()
                        else None
                    ),
                    category=random.choice(
                        [choice[0] for choice in Project.ProjectCategory.choices]
                    ),
                    status=random.choice(
                        [choice[0] for choice in Project.ProjectStatus.choices]
                    ),
                    technologies=fake.words(nb=5),
                )
                self.projects.append(project)

        # Create skills
        skill_names = [
            "Python",
            "JavaScript",
            "React",
            "Django",
            "SQL",
            "Machine Learning",
            "Project Management",
            "Leadership",
            "Communication",
            "Problem Solving",
        ]
        self.skills = []
        for user in random.sample(self.users, min(100, len(self.users))):
            user_skills = random.sample(skill_names, random.randint(3, 8))
            for skill_name in user_skills:
                skill = Skill.objects.create(
                    user=user,
                    name=skill_name,
                    category=random.choice(
                        ["Technical", "Soft Skills", "Languages", "Tools"]
                    ),
                    level=random.randint(1, 5),
                    years_of_experience=random.randint(1, 15),
                )
                self.skills.append(skill)

        # Create skill endorsements
        for _ in range(200):
            skill = random.choice(self.skills)
            endorser = random.choice([u for u in self.users if u != skill.user])
            try:
                SkillEndorsement.objects.create(
                    skill=skill,
                    endorser=endorser,
                    comment=fake.sentence() if fake.boolean() else "",
                )
            except:
                pass  # Skip if already exists

        # Create languages
        languages = [
            "English",
            "Spanish",
            "French",
            "German",
            "Chinese",
            "Japanese",
            "Arabic",
        ]
        for user in random.sample(self.users, min(100, len(self.users))):
            user_languages = random.sample(languages, random.randint(1, 4))
            for lang in user_languages:
                Language.objects.create(
                    user=user,
                    name=lang,
                    proficiency=random.choice(
                        [choice[0] for choice in Language.Proficiency.choices]
                    ),
                )

        # Create achievements
        for user in random.sample(self.users, min(100, len(self.users))):
            for _ in range(random.randint(1, 5)):
                Achievement.objects.create(
                    user=user,
                    title=fake.catch_phrase(),
                    description=fake.text(max_nb_chars=300),
                    date=fake.date_between(start_date="-5y", end_date="today"),
                    category=random.choice(
                        [
                            choice[0]
                            for choice in Achievement.AchievementCategory.choices
                        ]
                    ),
                    issuer=fake.company(),
                )

        # Create connections and follows
        for _ in range(300):
            user1, user2 = random.sample(self.users, 2)
            try:
                Connection.objects.create(
                    from_user=user1,
                    to_user=user2,
                    status=random.choice(
                        [choice[0] for choice in Connection.ConnectionStatus.choices]
                    ),
                    message=fake.sentence() if fake.boolean() else "",
                )
            except:
                pass

        for _ in range(500):
            follower, following = random.sample(self.users, 2)
            try:
                Follow.objects.create(follower=follower, following=following)
            except:
                pass

        # Create profile views
        for _ in range(1000):
            viewer = random.choice(self.users)
            viewed = random.choice([u for u in self.users if u != viewer])
            ProfileView.objects.create(
                viewer=viewer, profile_owner=viewed, ip_address=fake.ipv4()
            )

        # Create activity logs
        activity_types = [choice[0] for choice in ActivityLog.ActivityType.choices]
        for _ in range(500):
            ActivityLog.objects.create(
                user=random.choice(self.users),
                activity_type=random.choice(activity_types),
                description=fake.sentence(),
                ip_address=fake.ipv4(),
                user_agent=fake.user_agent(),
                metadata={"extra": fake.word()},
            )

        # Create tasks
        self.tasks = []
        for _ in range(200):
            task = Task.objects.create(
                title=fake.catch_phrase(),
                description=fake.text(max_nb_chars=500),
                assigned_to=random.choice(self.users),
                created_by=random.choice(self.users),
                due_date=fake.future_date(end_date="+30d"),
                status=random.choice([choice[0] for choice in Task.TaskStatus.choices]),
                priority=random.choice(
                    [choice[0] for choice in Task.TaskPriority.choices]
                ),
                estimated_hours=random.randint(1, 40),
                actual_hours=random.randint(1, 50) if fake.boolean() else None,
            )
            self.tasks.append(task)

        # Create task comments
        for _ in range(300):
            TaskComment.objects.create(
                task=random.choice(self.tasks),
                user=random.choice(self.users),
                comment=fake.text(max_nb_chars=500),
            )

        # Create networks
        self.networks = []
        for _ in range(20):
            network = Network.objects.create(
                name=fake.company(),
                description=fake.text(max_nb_chars=500),
                website=fake.url(),
                is_public=fake.boolean(),
                created_by=random.choice(self.users),
            )
            self.networks.append(network)

        # Create network memberships
        for _ in range(200):
            try:
                NetworkMembership.objects.create(
                    user=random.choice(self.users),
                    network=random.choice(self.networks),
                    status=random.choice(
                        [
                            choice[0]
                            for choice in NetworkMembership.MembershipStatus.choices
                        ]
                    ),
                )
            except:
                pass

    def create_common_data(self):
        """Create common app data"""
        self.stdout.write("Creating common data...")

        # Create tags
        self.tags = []
        tag_names = [
            "technology",
            "business",
            "marketing",
            "design",
            "development",
            "ai",
            "machine-learning",
            "web",
            "mobile",
            "startup",
        ]
        for name in tag_names:
            tag = Tag.objects.create(name=name, created_by=random.choice(self.users))
            self.tags.append(tag)

        # Create hierarchical tags
        for _ in range(20):
            Tag.objects.create(
                name=fake.word(),
                parent=random.choice(self.tags) if fake.boolean() else None,
                created_by=random.choice(self.users),
            )

        # Create actions
        action_types = [
            "login",
            "logout",
            "view_profile",
            "update_profile",
            "create_post",
        ]
        for _ in range(500):
            Action.objects.create(
                user=random.choice(self.users),
                action_type=random.choice(action_types),
                metadata={"ip": fake.ipv4(), "user_agent": fake.user_agent()},
            )

    def create_blog_data(self):
        """Create blog-related data"""
        self.stdout.write("Creating blog data...")

        # Create blog categories
        self.blog_categories = []
        categories = ["Technology", "Business", "Lifestyle", "Travel", "Food", "Health"]
        for category_name in categories:
            category = BlogCategory.objects.create(
                name=category_name,
                slug=category_name.lower(),
                description=fake.text(max_nb_chars=200),
                is_active=True,
                meta_title=category_name,
                meta_description=fake.text(max_nb_chars=150),
            )
            self.blog_categories.append(category)

        # Create subcategories
        for _ in range(10):
            BlogCategory.objects.create(
                name=fake.word().title(),
                slug=fake.slug(),
                parent=random.choice(self.blog_categories),
                description=fake.text(max_nb_chars=200),
                is_active=True,
            )

        # Create blog tags
        self.blog_tags = []
        for _ in range(50):
            tag = BlogTag.objects.create(
                name=fake.word(), description=fake.sentence(), color=fake.hex_color()
            )
            self.blog_tags.append(tag)

        # Create blog posts
        self.blog_posts = []
        for _ in range(200):
            post = BlogPost.objects.create(
                title=fake.catch_phrase(),
                slug=fake.unique.slug(),
                content=fake.text(max_nb_chars=2000),
                excerpt=fake.text(max_nb_chars=300),
                author=random.choice(self.users),
                category=random.choice(self.blog_categories),
                status=random.choice(
                    [choice[0] for choice in BlogPost.PostStatus.choices]
                ),
                visibility=random.choice(
                    [choice[0] for choice in BlogPost.Visibility.choices]
                ),
                content_format=random.choice(
                    [choice[0] for choice in BlogPost.ContentFormat.choices]
                ),
                post_type=random.choice(
                    [choice[0] for choice in BlogPost.PostType.choices]
                ),
                featured_image=None,  # Would need actual image
                is_featured=fake.boolean(chance_of_getting_true=10),
                allow_comments=fake.boolean(chance_of_getting_true=80),
                reading_time=random.randint(1, 30),
                view_count=random.randint(0, 10000),
                like_count=random.randint(0, 500),
                share_count=random.randint(0, 100),
                comment_count=random.randint(0, 50),
                published_at=(
                    fake.date_time_between(
                        start_date="-1y", end_date="now", tzinfo=dt_timezone.utc
                    )
                    if random.choice([True, False])
                    else None
                ),
                meta_title=fake.sentence(),
                meta_description=fake.text(max_nb_chars=150),
            )
            self.blog_posts.append(post)

        # Assign tags to posts
        for post in self.blog_posts:
            tags = random.sample(self.blog_tags, random.randint(1, 5))
            post.tags.set(tags)

        # Create blog comments
        self.blog_comments = []
        for _ in range(500):
            comment = BlogComment.objects.create(
                post=random.choice(self.blog_posts),
                author=random.choice(self.users),
                content=fake.text(max_nb_chars=500),
                status=random.choice(
                    [choice[0] for choice in BlogComment.CommentStatus.choices]
                ),
                ip_address=fake.ipv4(),
                user_agent=fake.user_agent(),
            )
            self.blog_comments.append(comment)

        # Create comment replies
        for _ in range(200):
            BlogComment.objects.create(
                post=random.choice(self.blog_posts),
                parent=random.choice(self.blog_comments),
                author=random.choice(self.users),
                content=fake.text(max_nb_chars=300),
                status=random.choice(
                    [choice[0] for choice in BlogComment.CommentStatus.choices]
                ),
                ip_address=fake.ipv4(),
                user_agent=fake.user_agent(),
            )

        # Create blog reactions
        reaction_types = [choice[0] for choice in BlogReaction.ReactionType.choices]
        for _ in range(1000):
            try:
                BlogReaction.objects.create(
                    post=random.choice(self.blog_posts),
                    user=random.choice(self.users),
                    reaction_type=random.choice(reaction_types),
                )
            except:
                pass  # Skip duplicates

        # Create blog views
        for _ in range(2000):
            try:
                BlogView.objects.create(
                    post=random.choice(self.blog_posts),
                    user=random.choice(self.users) if fake.boolean() else None,
                    ip_address=fake.ipv4(),
                    user_agent=fake.user_agent(),
                )
            except:
                pass

        # Create blog series
        self.blog_series = []
        for _ in range(20):
            series = BlogSeries.objects.create(
                title=fake.catch_phrase(),
                slug=fake.unique.slug(),
                description=fake.text(max_nb_chars=500),
                author=random.choice(self.users),
            )
            self.blog_series.append(series)

        # Assign posts to series
        for _ in range(100):
            try:
                BlogSeriesPost.objects.create(
                    series=random.choice(self.blog_series),
                    post=random.choice(self.blog_posts),
                    order=random.randint(1, 10),
                )
            except:
                pass

    def create_event_data(self):
        """Create event-related data"""
        self.stdout.write("Creating event data...")

        # Create event categories
        self.event_categories = []
        categories = ["Conference", "Workshop", "Seminar", "Networking", "Training"]
        for category_name in categories:
            category = EventCategory.objects.create(
                name=category_name,
                slug=category_name.lower(),
                description=fake.text(max_nb_chars=200),
                icon="fa-calendar",
                color=fake.hex_color(),
                is_active=True,
            )
            self.event_categories.append(category)

        # Create event tags
        self.event_tags = []
        for _ in range(30):
            tag = EventTag.objects.create(
                name=fake.word(), description=fake.sentence(), color=fake.hex_color()
            )
            self.event_tags.append(tag)

        # Create events
        self.events = []
        for _ in range(100):
            start_date = fake.future_datetime(end_date="+6M", tzinfo=dt_timezone.utc)
            end_date = start_date + timedelta(hours=random.randint(1, 48))

            event = Event.objects.create(
                title=fake.catch_phrase(),
                slug=fake.unique.slug(),
                description=fake.text(max_nb_chars=1000),
                short_description=fake.text(max_nb_chars=200),
                organizer=random.choice(self.users),
                event_type=random.choice(
                    [choice[0] for choice in Event.EventType.choices]
                ),
                status=random.choice(
                    [choice[0] for choice in Event.EventStatus.choices]
                ),
                visibility=random.choice(
                    [choice[0] for choice in Event.Visibility.choices]
                ),
                start_date=start_date,
                end_date=end_date,
                timezone="UTC",
                venue_name=fake.company(),
                venue_address=fake.address(),
                venue_city=fake.city(),
                venue_country=fake.country(),
                venue_coordinates=None,  # Would need proper coordinates
                online_url=fake.url() if fake.boolean() else "",
                capacity=random.randint(50, 1000),
                price=Decimal(random.randint(0, 500)),
                currency="USD",
                registration_start=fake.past_datetime(
                    start_date="-30d", tzinfo=dt_timezone.utc
                ),
                registration_end=start_date - timedelta(days=1),
                requires_approval=fake.boolean(),
                allow_waitlist=fake.boolean(),
                is_featured=fake.boolean(chance_of_getting_true=10),
                meta_title=fake.sentence(),
                meta_description=fake.text(max_nb_chars=150),
                view_count=random.randint(0, 5000),
                registration_count=random.randint(0, 500),
            )
            self.events.append(event)

        # Create event category relations
        for event in self.events:
            categories = random.sample(self.event_categories, random.randint(1, 2))
            for category in categories:
                EventCategoryRelation.objects.create(event=event, category=category)

        # Create event tag relations
        for event in self.events:
            tags = random.sample(self.event_tags, random.randint(0, 3))
            for tag in tags:
                EventTagRelation.objects.create(event=event, tag=tag)

        # Create sessions
        self.sessions = []
        for event in self.events:
            for _ in range(random.randint(1, 5)):
                session_start = event.start_date + timedelta(
                    hours=random.randint(0, 24)
                )
                session_end = session_start + timedelta(hours=random.randint(1, 4))

                session = Session.objects.create(
                    event=event,
                    title=fake.catch_phrase(),
                    description=fake.text(max_nb_chars=500),
                    speaker=random.choice(self.users),
                    session_type=random.choice(
                        [choice[0] for choice in Session.SessionType.choices]
                    ),
                    status=random.choice(
                        [choice[0] for choice in Session.SessionStatus.choices]
                    ),
                    start_time=session_start,
                    end_time=session_end,
                    location=fake.address(),
                    capacity=random.randint(20, 200),
                    price=Decimal(random.randint(0, 100)),
                    materials_url=fake.url() if fake.boolean() else "",
                    recording_url=fake.url() if fake.boolean() else "",
                    requires_registration=fake.boolean(),
                )
                self.sessions.append(session)

        # Create participants
        self.participants = []
        for _ in range(1000):
            participant = Participant.objects.create(
                event=random.choice(self.events),
                user=random.choice(self.users),
                role=random.choice([choice[0] for choice in Participant.Role.choices]),
                registration_status=random.choice(
                    [choice[0] for choice in Participant.RegistrationStatus.choices]
                ),
                attendance_status=random.choice(
                    [choice[0] for choice in Participant.AttendanceStatus.choices]
                ),
                check_in_time=(
                    fake.date_time_between(
                        start_date="-30d", end_date="now", tzinfo=dt_timezone.utc
                    )
                    if fake.boolean()
                    else None
                ),
                check_out_time=(
                    fake.date_time_between(
                        start_date="-30d", end_date="now", tzinfo=dt_timezone.utc
                    )
                    if fake.boolean()
                    else None
                ),
                points_earned=random.randint(0, 100),
                special_requirements=(
                    fake.text(max_nb_chars=200) if fake.boolean() else ""
                ),
                notes=fake.text(max_nb_chars=300) if fake.boolean() else "",
            )
            self.participants.append(participant)

        # Create exhibitors
        for _ in range(50):
            Exhibitor.objects.create(
                event=random.choice(self.events),
                user=random.choice(self.users),
                company_name=fake.company(),
                company_description=fake.text(max_nb_chars=500),
                website=fake.url(),
                contact_email=fake.email(),
                contact_phone=fake.phone_number(),
                sponsorship_tier=random.choice(
                    [choice[0] for choice in Exhibitor.SponsorshipTier.choices]
                ),
                status=random.choice(
                    [choice[0] for choice in Exhibitor.ExhibitorStatus.choices]
                ),
                booth_number=f"B{random.randint(1, 100)}",
                booth_size="3x3",
                payment_amount=Decimal(random.randint(500, 5000)),
                special_requirements=(
                    fake.text(max_nb_chars=200) if fake.boolean() else ""
                ),
            )

    def create_chat_data(self):
        """Create chat-related data"""
        self.stdout.write("Creating chat data...")

        # Create chats
        self.chats = []
        for _ in range(50):
            chat = Chat.objects.create(
                name=fake.company() if fake.boolean() else None,
                description=fake.text(max_nb_chars=300) if fake.boolean() else "",
                chat_type=random.choice(
                    [choice[0] for choice in Chat.ChatType.choices]
                ),
                status=random.choice([choice[0] for choice in Chat.ChatStatus.choices]),
                creator=random.choice(self.users),
                is_public=fake.boolean(),
                max_participants=random.randint(2, 1000) if fake.boolean() else None,
                slow_mode_enabled=fake.boolean(),
                slow_mode_interval=(
                    random.choice(
                        [choice[0] for choice in Chat.SlowModeInterval.choices]
                    )
                    if fake.boolean()
                    else None
                ),
                pin_message_enabled=fake.boolean(),
                auto_delete_messages=fake.boolean(),
                auto_delete_duration=random.randint(1, 30) if fake.boolean() else None,
            )
            self.chats.append(chat)

        # Create chat participants
        self.chat_participants = []
        for chat in self.chats:
            # Add creator as admin
            participant = ChatParticipant.objects.create(
                chat=chat,
                user=chat.creator,
                role=ChatParticipant.ParticipantRole.ADMIN,
                status=ChatParticipant.ParticipantStatus.ACTIVE,
                notification_level=random.choice(
                    [choice[0] for choice in ChatParticipant.NotificationLevel.choices]
                ),
            )
            self.chat_participants.append(participant)

            # Add other participants
            other_users = random.sample(
                [u for u in self.users if u != chat.creator],
                random.randint(1, min(10, len(self.users) - 1)),
            )
            for user in other_users:
                participant = ChatParticipant.objects.create(
                    chat=chat,
                    user=user,
                    role=random.choice(
                        [
                            choice[0]
                            for choice in ChatParticipant.ParticipantRole.choices
                        ]
                    ),
                    status=random.choice(
                        [
                            choice[0]
                            for choice in ChatParticipant.ParticipantStatus.choices
                        ]
                    ),
                    notification_level=random.choice(
                        [
                            choice[0]
                            for choice in ChatParticipant.NotificationLevel.choices
                        ]
                    ),
                    muted_until=(
                        fake.future_datetime(end_date="+7d", tzinfo=dt_timezone.utc)
                        if fake.boolean(chance_of_getting_true=10)
                        else None
                    ),
                )
                self.chat_participants.append(participant)

        # Create chat messages
        self.chat_messages = []
        for _ in range(1000):
            chat = random.choice(self.chats)
            participant = random.choice(
                [p for p in self.chat_participants if p.chat == chat]
            )

            message = ChatMessage.objects.create(
                chat=chat,
                user=participant.user,
                content=fake.text(max_nb_chars=500),
                message_type=random.choice(
                    [choice[0] for choice in ChatMessage.MessageType.choices]
                ),
                status=random.choice(
                    [choice[0] for choice in ChatMessage.MessageStatus.choices]
                ),
                reply_to=(
                    random.choice(self.chat_messages)
                    if self.chat_messages and fake.boolean(chance_of_getting_true=20)
                    else None
                ),
                edit_count=(
                    random.randint(0, 3)
                    if fake.boolean(chance_of_getting_true=10)
                    else 0
                ),
                metadata={"client": fake.user_agent()},
            )
            self.chat_messages.append(message)

        # Create chat themes
        for _ in range(10):
            ChatTheme.objects.create(
                name=fake.color_name(),
                primary_color=fake.hex_color(),
                secondary_color=fake.hex_color(),
                background_color=fake.hex_color(),
                text_color=fake.hex_color(),
                is_default=fake.boolean(chance_of_getting_true=10),
                created_by=random.choice(self.users),
            )

        # Create sticker sets
        self.sticker_sets = []
        for _ in range(10):
            sticker_set = ChatStickerSet.objects.create(
                name=fake.word(),
                description=fake.sentence(),
                sticker_type=random.choice(
                    [choice[0] for choice in ChatStickerSet.StickerType.choices]
                ),
                is_public=fake.boolean(),
                created_by=random.choice(self.users),
            )
            self.sticker_sets.append(sticker_set)

        # Create stickers
        for sticker_set in self.sticker_sets:
            for _ in range(random.randint(5, 20)):
                ChatSticker.objects.create(
                    sticker_set=sticker_set,
                    name=fake.word(),
                    emoji=random.choice(
                        ["😀", "😃", "😄", "😁", "😆", "😅", "😂", "🤣"]
                    ),
                    # file_path would need actual file
                )

    def create_payment_data(self):
        """Create payment-related data"""
        self.stdout.write("Creating payment data...")

        # Create payment gateway configs
        self.gateways = []
        gateway_names = ["PayPal", "Stripe", "Square", "Bank Transfer"]
        for name in gateway_names:
            gateway = PaymentGatewayConfig.objects.create(
                name=name,
                merchant_id=fake.uuid4(),
                api_key=fake.uuid4(),
                callback_url=fake.url(),
                is_active=fake.boolean(chance_of_getting_true=80),
            )
            self.gateways.append(gateway)

        # Create payments
        self.payments = []
        for _ in range(300):
            payment = Payment.objects.create(
                user=random.choice(self.users),
                gateway=random.choice(self.gateways),
                amount=Decimal(random.uniform(10.0, 1000.0)).quantize(Decimal("0.01")),
                currency=random.choice(
                    [choice[0] for choice in Payment.Currency.choices]
                ),
                status=random.choice([choice[0] for choice in Payment.Status.choices]),
                token=fake.uuid4() if fake.boolean() else "",
                metadata={"order_id": fake.uuid4(), "product": fake.word()},
            )
            self.payments.append(payment)

        # Create transactions
        for payment in self.payments:
            for _ in range(random.randint(1, 3)):
                Transaction.objects.create(
                    payment=payment,
                    status=random.choice(
                        [choice[0] for choice in Transaction.Status.choices]
                    ),
                    bank_response={"status": "success", "reference": fake.uuid4()},
                    error_message=(
                        fake.sentence()
                        if fake.boolean(chance_of_getting_true=20)
                        else ""
                    ),
                )

        # Create refunds
        for _ in range(50):
            payment = random.choice(
                [p for p in self.payments if p.status == Payment.Status.SUCCESS]
            )
            Refund.objects.create(
                payment=payment,
                user=payment.user,
                amount=payment.amount / 2,  # Partial refund
                reason=fake.text(max_nb_chars=200),
                status=random.choice(["PENDING", "APPROVED", "REJECTED"]),
            )

    def create_notification_data(self):
        """Create notification-related data"""
        self.stdout.write("Creating notification data...")

        # Create notification templates
        self.templates = []
        template_names = [
            "welcome_message",
            "password_reset",
            "payment_confirmation",
            "event_reminder",
            "new_message",
            "profile_view",
        ]
        for name in template_names:
            template = NotificationTemplate.objects.create(
                name=name,
                subject=f"Template: {name.replace('_', ' ').title()}",
                message=f"Hello {{username}}, this is a {name.replace('_', ' ')} notification.",
                category=random.choice(["system", "marketing", "transactional"]),
            )
            self.templates.append(template)

        # Create notification batches
        self.batches = []
        for _ in range(20):
            batch = NotificationBatch.objects.create(
                description=fake.catch_phrase(), created_by=random.choice(self.users)
            )
            self.batches.append(batch)

        # Create notifications
        for _ in range(1000):
            Notification.objects.create(
                user=random.choice(self.users),
                template=random.choice(self.templates) if fake.boolean() else None,
                batch=random.choice(self.batches) if fake.boolean() else None,
                message=fake.text(max_nb_chars=500),
                subject=fake.sentence() if fake.boolean() else "",
                priority=random.choice(
                    [choice[0] for choice in Notification.Priority.choices]
                ),
                channels=[
                    random.choice(
                        [choice[0] for choice in Notification.Channel.choices]
                    )
                ],
                category=random.choice(["system", "marketing", "transactional"]),
                status=random.choice(
                    [choice[0] for choice in Notification.Status.choices]
                ),
                metadata={"link": fake.url(), "action": fake.word()},
                is_read=fake.boolean(chance_of_getting_true=30),
                expires_at=(
                    fake.future_datetime(end_date="+30d", tzinfo=dt_timezone.utc)
                    if fake.boolean()
                    else None
                ),
                sent_at=(
                    fake.past_datetime(start_date="-30d", tzinfo=dt_timezone.utc)
                    if fake.boolean()
                    else None
                ),
                read_at=(
                    fake.past_datetime(start_date="-30d", tzinfo=dt_timezone.utc)
                    if fake.boolean()
                    else None
                ),
            )

    def create_feedback_data(self):
        """Create feedback data"""
        self.stdout.write("Creating feedback data...")

        # Create feedback
        for _ in range(200):
            Feedback.objects.create(
                user=(
                    random.choice(self.users)
                    if fake.boolean(chance_of_getting_true=70)
                    else None
                ),
                feedback_type=random.choice(
                    [choice[0] for choice in Feedback.FeedbackType.choices]
                ),
                status=random.choice([choice[0] for choice in Feedback.Status.choices]),
                title=fake.catch_phrase(),
                description=fake.text(max_nb_chars=1000),
                metadata={
                    "browser": fake.user_agent(),
                    "page_url": fake.url(),
                    "user_agent": fake.user_agent(),
                    "ip_address": fake.ipv4(),
                },
            )

    def create_audit_data(self):
        """Create audit log data"""
        self.stdout.write("Creating audit data...")

        # Create audit logs
        action_types = [choice[0] for choice in AuditLog.ActionType.choices]
        for _ in range(1000):
            AuditLog.objects.create(
                user=(
                    random.choice(self.users)
                    if fake.boolean(chance_of_getting_true=80)
                    else None
                ),
                action_type=random.choice(action_types),
                status=random.choice([choice[0] for choice in AuditLog.Status.choices]),
                priority=random.choice(
                    [choice[0] for choice in AuditLog.Priority.choices]
                ),
                ip_address=fake.ipv4(),
                user_agent=fake.user_agent(),
                content_type=(
                    ContentType.objects.get_for_model(random.choice(self.users))
                    if fake.boolean()
                    else None
                ),
                object_id=random.choice(self.users).id if fake.boolean() else None,
                object_repr=fake.sentence(),
                changes=(
                    {
                        "before": {"status": "old_value"},
                        "after": {"status": "new_value"},
                    }
                    if fake.boolean()
                    else {}
                ),
                metadata={
                    "request_method": random.choice(["GET", "POST", "PUT", "DELETE"]),
                    "request_url": fake.url(),
                    "response_status": random.choice([200, 201, 400, 404, 500]),
                },
                error_message=(
                    fake.sentence() if fake.boolean(chance_of_getting_true=20) else ""
                ),
            )
