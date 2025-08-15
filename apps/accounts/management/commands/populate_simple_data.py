import random
import uuid
from datetime import timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from faker import Faker

# Import all models from all apps
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
    BlogReadingList,
    BlogReaction,
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


class Command(BaseCommand):
    help = "Populate database with comprehensive test data for all models and relations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--users", type=int, default=50, help="Number of users to create"
        )
        parser.add_argument(
            "--clear", action="store_true", help="Clear existing data before populating"
        )

    def handle(self, *args, **options):
        self.stdout.write("Starting data population...")

        if options["clear"]:
            self.clear_data()

        # Create base data first
        self.create_base_data()

        # Create users and account-related data
        self.create_account_data(options["users"])

        # Create content data
        self.create_common_data()
        self.create_blog_data()
        self.create_event_data()
        self.create_chat_data()
        self.create_payment_data()
        self.create_notification_data()
        self.create_feedback_data()
        self.create_audit_data()

        self.stdout.write("Successfully populated database with test data!")

    def clear_data(self):
        """Clear all existing data."""
        self.stdout.write("Clearing existing data...")

        # Clear in reverse dependency order
        models_to_clear = [
            # Related models first
            AuditLog,
            UserBlogBadge,
            BlogModerationLog,
            BlogReadingList,
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
            BlogNewsletter,
            BlogBadge,
            BlogTag,
            BlogCategory,
            # Chat models
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
            # Event models
            EventModerationLog,
            EventView,
            EventFavorite,
            SessionRating,
            EventAttachment,
            ParticipantBadge,
            EventBadge,
            Product,
            Exhibitor,
            Participant,
            Session,
            EventTagRelation,
            EventCategoryRelation,
            EventAnalytics,
            Event,
            EventTag,
            EventCategory,
            # Payment models
            Refund,
            Transaction,
            Payment,
            PaymentGatewayConfig,
            # Notification models
            Notification,
            NotificationBatch,
            NotificationTemplate,
            # Feedback models
            Feedback,
            # Common models
            View,
            React,
            Comment,
            Action,
            Tag,
            # Account models
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
        ]

        for model in models_to_clear:
            try:
                count = model.objects.count()
                if count > 0:
                    model.objects.all().delete()
                    self.stdout.write(f"Deleted {count} {model.__name__} objects")
            except Exception as e:
                self.stdout.write(f"Warning: Error deleting {model.__name__}: {e}")

        # Clear users last (except superusers)
        user_count = User.objects.filter(is_superuser=False).count()
        if user_count > 0:
            User.objects.filter(is_superuser=False).delete()
            self.stdout.write(f"Deleted {user_count} regular users")

    def safe_create(self, model_class, **kwargs):
        """Safely create model instance with error handling."""
        try:
            return model_class.objects.create(**kwargs)
        except Exception as e:
            self.stdout.write(f"Warning: Failed to create {model_class.__name__}: {e}")
            return None

    def create_base_data(self):
        """Create base system data like roles, departments, etc."""
        self.stdout.write("Creating base system data...")

        # Create roles
        roles_data = [
            {
                "name": "Admin",
                "description": "System administrator with full access",
                "is_system_role": True,
            },
            {
                "name": "Moderator",
                "description": "Content moderator",
                "is_system_role": True,
            },
            {
                "name": "Event Organizer",
                "description": "Can create and manage events",
                "is_system_role": False,
            },
            {
                "name": "Content Creator",
                "description": "Can create blog posts and content",
                "is_system_role": False,
            },
            {
                "name": "Premium User",
                "description": "Premium subscription user",
                "is_system_role": False,
            },
        ]

        for role_data in roles_data:
            self.safe_create(Role, **role_data)

        # Create departments
        departments_data = [
            {"name": "Engineering", "description": "Software development team"},
            {"name": "Marketing", "description": "Marketing and promotion team"},
            {"name": "Sales", "description": "Sales and business development"},
            {"name": "HR", "description": "Human resources"},
            {"name": "Finance", "description": "Financial management"},
        ]

        for dept_data in departments_data:
            self.safe_create(Department, **dept_data)

        # Create sub-departments
        engineering = Department.objects.filter(name="Engineering").first()
        if engineering:
            sub_depts = [
                {"name": "Frontend", "parent": engineering},
                {"name": "Backend", "parent": engineering},
                {"name": "DevOps", "parent": engineering},
                {"name": "QA", "parent": engineering},
            ]
            for sub_dept in sub_depts:
                self.safe_create(Department, **sub_dept)

        # Create common tags
        common_tags = [
            "Technology",
            "Business",
            "Education",
            "Health",
            "Science",
            "Art",
            "Music",
            "Sports",
            "Travel",
            "Food",
            "Fashion",
            "Programming",
            "Design",
            "Marketing",
            "Finance",
        ]

        for tag_name in common_tags:
            self.safe_create(Tag, name=tag_name, slug=tag_name.lower())

        # Create payment gateway configs
        gateway_configs = [
            {
                "name": "ZarinPal",
                "merchant_id": "test-merchant-zarinpal",
                "api_key": "test-api-key-zarinpal",
                "callback_url": "https://example.com/payment/zarinpal/callback/",
                "is_active": True,
            },
            {
                "name": "IDPay",
                "merchant_id": "test-merchant-idpay",
                "api_key": "test-api-key-idpay",
                "callback_url": "https://example.com/payment/idpay/callback/",
                "is_active": True,
            },
        ]

        for config in gateway_configs:
            self.safe_create(PaymentGatewayConfig, **config)

        self.stdout.write("Base data created successfully")

    def create_account_data(self, num_users):
        """Create comprehensive user accounts and related data."""
        self.stdout.write(f"Creating {num_users} users and account data...")

        User = get_user_model()
        users = []
        roles = list(Role.objects.all())
        departments = list(Department.objects.all())

        # Create users with different roles
        for i in range(num_users):
            user_data = {
                "username": fake.user_name(),
                "email": fake.email(),
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "is_active": True,
                "date_joined": fake.date_time_between(
                    start_date="-2y", end_date="now", tzinfo=dt_timezone.utc
                ),
            }

            user = self.safe_create(User, **user_data)
            if user:
                user.set_password("testpass123")
                user.save()
                users.append(user)

        # Update user profiles (they are created automatically by signals)
        for user in users:
            try:
                profile = user.profile
                profile.display_name = fake.name()
                profile.bio = fake.text(max_nb_chars=500)
                profile.location = fake.city()
                profile.website = fake.url()
                profile.phone = fake.phone_number()
                profile.date_of_birth = fake.date_of_birth(
                    minimum_age=18, maximum_age=70
                )
                profile.show_email = random.choice([True, False])
                profile.show_phone = random.choice([True, False])
                profile.save()
            except Exception as e:
                self.stdout.write(
                    f"Warning: Failed to update profile for {user.username}: {e}"
                )

        # Assign roles to users
        for user in users:
            if random.random() < 0.3:  # 30% chance to have a role
                role = random.choice(roles)
                self.safe_create(
                    UserRole,
                    user=user,
                    role=role,
                    assigned_by=random.choice(users),
                    assigned_at=timezone.now(),
                )

        # Assign departments
        for user in users:
            if random.random() < 0.6:  # 60% chance to have a department
                department = random.choice(departments)
                self.safe_create(
                    UserDepartment,
                    user=user,
                    department=department,
                    position=fake.job(),
                    is_primary=True,
                )

        # Create social links
        platforms = ["linkedin", "github", "twitter", "instagram", "website"]
        for user in users[:20]:  # Only for first 20 users
            for platform in random.sample(platforms, random.randint(1, 3)):
                self.safe_create(
                    SocialLink,
                    user=user,
                    platform=platform,
                    url=fake.url(),
                    is_visible=random.choice([True, False]),
                )

        # Create experiences
        for user in users[:30]:
            for _ in range(random.randint(1, 4)):
                start_date = fake.date_between(start_date="-10y", end_date="-1y")
                end_date = (
                    fake.date_between(start_date=start_date, end_date="today")
                    if random.random() < 0.8
                    else None
                )

                self.safe_create(
                    Experience,
                    user=user,
                    title=fake.job(),
                    company=fake.company(),
                    description=fake.text(max_nb_chars=500),
                    start_date=start_date,
                    end_date=end_date,
                    is_current=end_date is None,
                    type=random.choice(Experience.ExperienceType.choices)[0],
                )

        # Create education
        for user in users[:25]:
            for _ in range(random.randint(1, 3)):
                start_date = fake.date_between(start_date="-15y", end_date="-5y")
                end_date = (
                    fake.date_between(start_date=start_date, end_date="-2y")
                    if random.random() < 0.9
                    else None
                )

                self.safe_create(
                    Education,
                    user=user,
                    institution=fake.company(),
                    degree=random.choice(["Bachelor", "Master", "PhD", "Diploma"]),
                    field_of_study=fake.job(),
                    start_date=start_date,
                    end_date=end_date,
                    is_current=end_date is None,
                )

        # Create certifications
        for user in users[:20]:
            for _ in range(random.randint(1, 3)):
                issue_date = fake.date_between(start_date="-5y", end_date="today")
                expiration_date = (
                    fake.date_between(start_date=issue_date, end_date="+3y")
                    if random.random() < 0.7
                    else None
                )

                self.safe_create(
                    Certification,
                    user=user,
                    name=f"{fake.word().title()} Certification",
                    issuer=fake.company(),
                    issue_date=issue_date,
                    expiration_date=expiration_date,
                    credential_id=fake.bothify(text="????-####"),
                    credential_url=fake.url(),
                )

        # Create projects
        for user in users[:35]:
            for _ in range(random.randint(1, 5)):
                project = self.safe_create(
                    Project,
                    user=user,
                    title=fake.catch_phrase(),
                    description=fake.text(max_nb_chars=1000),
                    technologies=fake.words(nb=5),
                    url=fake.url() if random.random() < 0.7 else "",
                    github_url=fake.url() if random.random() < 0.5 else "",
                    category=random.choice(Project.ProjectCategory.choices)[0],
                    status=random.choice(Project.ProjectStatus.choices)[0],
                    start_date=fake.date_between(start_date="-2y", end_date="today"),
                    end_date=fake.date_between(start_date="-1y", end_date="today")
                    if random.random() < 0.6
                    else None,
                )

                # Add project images
                if project and random.random() < 0.4:
                    for i in range(random.randint(1, 3)):
                        self.safe_create(
                            ProjectImage,
                            project=project,
                            caption=fake.sentence(),
                            order=i,
                        )

        # Create skills
        skill_categories = ["Programming", "Design", "Management", "Languages", "Tools"]
        common_skills = [
            "Python",
            "JavaScript",
            "React",
            "Django",
            "Docker",
            "AWS",
            "Project Management",
            "Team Leadership",
            "Communication",
            "Photoshop",
            "Figma",
            "SQL",
            "Git",
            "Linux",
        ]

        for user in users[:40]:
            for _ in range(random.randint(3, 8)):
                skill = self.safe_create(
                    Skill,
                    user=user,
                    name=random.choice(common_skills),
                    category=random.choice(skill_categories),
                    level=random.randint(1, 5),
                    years_of_experience=random.randint(0, 10),
                )

        # Create skill endorsements
        skills = list(Skill.objects.all())
        if (
            skills and len(users) > 1
        ):  # Only create endorsements if skills exist and we have multiple users
            for _ in range(min(50, len(skills) * 2)):  # Limit endorsements
                skill = random.choice(skills)
                potential_endorsers = [u for u in users if u != skill.user]
                if potential_endorsers:
                    endorser = random.choice(potential_endorsers)
                    # Check if endorsement already exists
                    if not SkillEndorsement.objects.filter(
                        skill=skill, endorser=endorser
                    ).exists():
                        self.safe_create(
                            SkillEndorsement,
                            skill=skill,
                            endorser=endorser,
                            message=fake.sentence() if random.random() < 0.5 else "",
                        )

        # Create languages
        common_languages = [
            "English",
            "Persian",
            "Spanish",
            "French",
            "German",
            "Chinese",
            "Arabic",
        ]
        for user in users[:30]:
            for _ in range(random.randint(1, 4)):
                self.safe_create(
                    Language,
                    user=user,
                    name=random.choice(common_languages),
                    proficiency=random.choice(Language.Proficiency.choices)[0],
                )

        # Create achievements
        for user in users[:25]:
            for _ in range(random.randint(1, 3)):
                self.safe_create(
                    Achievement,
                    user=user,
                    title=fake.catch_phrase(),
                    description=fake.text(max_nb_chars=500),
                    date=fake.date_between(start_date="-5y", end_date="today"),
                    issuer=fake.company(),
                    category=random.choice(Achievement.AchievementCategory.choices)[0],
                )

        # Create publications
        for user in users[:15]:
            for _ in range(random.randint(1, 3)):
                self.safe_create(
                    Publication,
                    user=user,
                    title=fake.catch_phrase(),
                    description=fake.text(max_nb_chars=800),
                    publication_date=fake.date_between(
                        start_date="-3y", end_date="today"
                    ),
                    publisher=fake.company(),
                    url=fake.url() if random.random() < 0.8 else "",
                    category=random.choice(Publication.PublicationCategory.choices)[0],
                )

        # Create volunteer work
        for user in users[:20]:
            for _ in range(random.randint(1, 2)):
                start_date = fake.date_between(start_date="-5y", end_date="-1y")
                end_date = (
                    fake.date_between(start_date=start_date, end_date="today")
                    if random.random() < 0.7
                    else None
                )

                self.safe_create(
                    Volunteer,
                    user=user,
                    organization=fake.company(),
                    role=fake.job(),
                    cause=fake.word(),
                    description=fake.text(max_nb_chars=500),
                    start_date=start_date,
                    end_date=end_date,
                    is_current=end_date is None,
                )

        # Create connections
        for _ in range(200):
            from_user = random.choice(users)
            to_user = random.choice([u for u in users if u != from_user])

            # Check if connection already exists
            if (
                not Connection.objects.filter(
                    from_user=from_user, to_user=to_user
                ).exists()
                and not Connection.objects.filter(
                    from_user=to_user, to_user=from_user
                ).exists()
            ):
                self.safe_create(
                    Connection,
                    from_user=from_user,
                    to_user=to_user,
                    status=random.choice(Connection.ConnectionStatus.choices)[0],
                    message=fake.sentence() if random.random() < 0.3 else "",
                )

        # Create follows
        for _ in range(300):
            follower = random.choice(users)
            following = random.choice([u for u in users if u != follower])

            if not Follow.objects.filter(
                follower=follower, following=following
            ).exists():
                self.safe_create(Follow, follower=follower, following=following)

        # Create profile views
        for _ in range(500):
            viewer = random.choice(users) if random.random() < 0.8 else None
            profile_owner = random.choice(users)

            if not viewer or viewer != profile_owner:
                self.safe_create(
                    ProfileView,
                    viewer=viewer,
                    profile_owner=profile_owner,
                    ip_address=fake.ipv4(),
                    user_agent=fake.user_agent(),
                )

        # Create user files
        for user in users[:20]:
            for _ in range(random.randint(1, 3)):
                self.safe_create(
                    UserFile,
                    user=user,
                    name=f"{fake.word().title()} File",
                    description=fake.sentence(),
                    file_type=random.choice(UserFile.FileType.choices)[0],
                    is_public=random.choice([True, False]),
                )

        # Create activity logs
        for user in users:
            for _ in range(random.randint(5, 20)):
                self.safe_create(
                    ActivityLog,
                    user=user,
                    activity_type=random.choice(ActivityLog.ActivityType.choices)[0],
                    description=fake.sentence(),
                    ip_address=fake.ipv4(),
                    user_agent=fake.user_agent(),
                    metadata={"action": fake.word(), "target": fake.word()},
                )

        # Create networks
        for _ in range(10):
            self.safe_create(
                Network,
                name=fake.company(),
                description=fake.text(max_nb_chars=500),
                industry=fake.word(),
                location=fake.city(),
                website=fake.url(),
                is_verified=random.choice([True, False]),
                is_public=random.choice([True, False]),
                created_by=random.choice(users),
            )

        # Create network memberships
        networks = list(Network.objects.all())
        if networks:
            for user in users[: min(30, len(users))]:
                for _ in range(random.randint(1, min(3, len(networks)))):
                    network = random.choice(networks)
                    if not NetworkMembership.objects.filter(
                        user=user, network=network
                    ).exists():
                        self.safe_create(
                            NetworkMembership,
                            user=user,
                            network=network,
                            status=random.choice(
                                NetworkMembership.MembershipStatus.choices
                            )[0],
                            role=fake.job(),
                        )

        # Create recommendations
        for _ in range(100):
            recommender = random.choice(users)
            recommendee = random.choice([u for u in users if u != recommender])

            self.safe_create(
                Recommendation,
                recommender=recommender,
                recommendee=recommendee,
                recommendation_type=random.choice(
                    Recommendation.RecommendationType.choices
                )[0],
                content=fake.text(max_nb_chars=1000),
                relationship=fake.sentence(),
                is_featured=random.choice([True, False]),
            )

        # Create messages
        for _ in range(200):
            sender = random.choice(users)
            recipient = random.choice([u for u in users if u != sender])

            self.safe_create(
                Message,
                sender=sender,
                recipient=recipient,
                subject=fake.sentence(),
                content=fake.text(max_nb_chars=1000),
                status=random.choice(Message.MessageStatus.choices)[0],
            )

        # Create tasks
        for user in users[:20]:
            for _ in range(random.randint(1, 5)):
                due_date = (
                    fake.date_between(start_date="today", end_date="+30d")
                    if random.random() < 0.7
                    else None
                )
                task = self.safe_create(
                    Task,
                    title=fake.sentence(),
                    description=fake.text(max_nb_chars=500),
                    assignee=user,
                    assigner=random.choice(users),
                    status=random.choice(Task.TaskStatus.choices)[0],
                    priority=random.choice(Task.TaskPriority.choices)[0],
                    due_date=due_date,
                    estimated_hours=random.randint(1, 40),
                )

                # Add task comments
                if task:
                    for _ in range(random.randint(0, 5)):
                        self.safe_create(
                            TaskComment,
                            task=task,
                            user=random.choice([user, task.assigner]),
                            content=fake.text(max_nb_chars=300),
                        )

        # Create resumes
        for user in users[:15]:
            self.safe_create(
                Resume,
                user=user,
                title=f"{user.first_name}'s Resume",
                summary=fake.text(max_nb_chars=500),
                status=random.choice(Resume.ResumeStatus.choices)[0],
                template_name="default",
                settings={"theme": "modern", "color": "blue"},
                is_default=True,
            )

        # Create profile stats
        for user in users:
            self.safe_create(
                ProfileStats,
                user=user,
                profile_views=random.randint(0, 1000),
                profile_views_this_week=random.randint(0, 50),
                profile_views_this_month=random.randint(0, 200),
                connections_count=random.randint(0, 500),
                endorsements_count=random.randint(0, 100),
                project_views=random.randint(0, 2000),
                search_appearances=random.randint(0, 500),
            )

        # Create saved searches
        for user in users[:10]:
            for _ in range(random.randint(1, 3)):
                self.safe_create(
                    SavedSearch,
                    user=user,
                    name=f"Search for {fake.word()}",
                    query_params={"q": fake.word(), "category": fake.word()},
                    alert_enabled=random.choice([True, False]),
                )

        self.stdout.write("Account data created successfully")

    def create_common_data(self):
        """Create common models data."""
        self.stdout.write("Creating common data...")

        users = list(User.objects.all())
        list(Tag.objects.all())

        # Create actions
        for user in users:
            for _ in range(random.randint(10, 50)):
                self.safe_create(
                    Action,
                    user=user,
                    action_type=random.choice(
                        ["view", "like", "share", "comment", "follow"]
                    ),
                    metadata={"target": fake.word(), "value": fake.word()},
                )

        # We'll create reactions and views when we have content to react to
        self.stdout.write("Common data created successfully")

    def create_blog_data(self):
        """Create comprehensive blog data."""
        self.stdout.write("Creating blog data...")

        users = list(User.objects.all())

        # Create blog categories
        category_data = [
            {"name": "Technology", "description": "Tech articles and tutorials"},
            {"name": "Business", "description": "Business insights and strategies"},
            {
                "name": "Programming",
                "description": "Coding tutorials and best practices",
            },
            {"name": "Design", "description": "UI/UX and graphic design"},
            {"name": "Career", "description": "Career advice and development"},
            {"name": "Tutorials", "description": "Step-by-step guides"},
        ]

        blog_categories = []
        for cat_data in category_data:
            category = self.safe_create(
                BlogCategory,
                name=cat_data["name"],
                slug=cat_data["name"].lower(),
                description=cat_data["description"],
                is_active=True,
            )
            if category:
                blog_categories.append(category)

        # Create subcategories
        if blog_categories:
            tech_category = next(
                (c for c in blog_categories if c.name == "Technology"), None
            )
            if tech_category:
                subcategories = [
                    {"name": "Web Development", "parent": tech_category},
                    {"name": "Mobile Development", "parent": tech_category},
                    {"name": "DevOps", "parent": tech_category},
                ]
                for subcat in subcategories:
                    self.safe_create(
                        BlogCategory,
                        slug=subcat["name"].lower().replace(" ", "-"),
                        **subcat,
                    )

        # Create blog tags
        blog_tag_names = [
            "Python",
            "JavaScript",
            "React",
            "Django",
            "Vue",
            "Angular",
            "Tutorial",
            "Beginner",
            "Advanced",
            "Tips",
            "Best Practices",
            "API",
            "Database",
            "Security",
            "Performance",
            "Frontend",
            "Backend",
        ]

        blog_tags = []
        for tag_name in blog_tag_names:
            tag = self.safe_create(
                BlogTag,
                name=tag_name,
                slug=tag_name.lower().replace(" ", "-"),
                description=f"Posts about {tag_name}",
                color=fake.hex_color(),
            )
            if tag:
                blog_tags.append(tag)

        # Create blog posts
        blog_posts = []
        for _ in range(100):
            publish_date = fake.date_time_between(
                start_date="-1y", end_date="now", tzinfo=dt_timezone.utc
            )
            post = self.safe_create(
                BlogPost,
                title=fake.catch_phrase(),
                slug=fake.unique.slug(),
                content=fake.text(max_nb_chars=3000),
                excerpt=fake.text(max_nb_chars=300),
                author=random.choice(users),
                status=random.choice(BlogPost.PostStatus.choices)[0],
                visibility=random.choice(BlogPost.Visibility.choices)[0],
                content_format=random.choice(BlogPost.ContentFormat.choices)[0],
                post_type=random.choice(BlogPost.PostType.choices)[0],
                is_featured=random.choice([True, False]),
                allow_comments=random.choice([True, False]),
                reading_time=random.randint(2, 15),
                publish_date=publish_date,
            )
            if post:
                blog_posts.append(post)
        print(blog_posts)
        # Assign categories and tags to posts
        for post in blog_posts:
            if blog_categories and random.random() < 0.8:
                post.categories.add(random.choice(blog_categories))

            if blog_tags:
                post_tags = random.sample(blog_tags, random.randint(1, 5))
                post.tags.set(post_tags)

        # Create blog post versions
        for post in blog_posts[:20]:
            for version in range(1, random.randint(2, 5)):
                self.safe_create(
                    BlogPostVersion,
                    post=post,
                    version_number=version,
                    title=post.title,
                    content=fake.text(max_nb_chars=2500),
                    change_summary=fake.sentence(),
                    created_by=post.author,
                )

        # Create blog comments
        for post in blog_posts:
            for _ in range(random.randint(0, 10)):
                comment = self.safe_create(
                    BlogComment,
                    post=post,
                    author=random.choice(users),
                    content=fake.text(max_nb_chars=500),
                    status=random.choice(BlogComment.CommentStatus.choices)[0],
                    is_approved=random.choice([True, False]),
                )

                # Create nested comments (replies)
                if comment and random.random() < 0.3:
                    self.safe_create(
                        BlogComment,
                        post=post,
                        author=random.choice(users),
                        parent=comment,
                        content=fake.text(max_nb_chars=300),
                        status=random.choice(BlogComment.CommentStatus.choices)[0],
                        is_approved=True,
                    )

        # Create blog reactions
        for post in blog_posts:
            for _ in range(random.randint(5, 50)):
                if random.random() < 0.8:  # 80% chance for posts
                    self.safe_create(
                        BlogReaction,
                        content_object=post,
                        user=random.choice(users),
                        reaction_type=random.choice(BlogReaction.ReactionType.choices)[
                            0
                        ],
                    )

        # Create blog views
        for post in blog_posts:
            for _ in range(random.randint(10, 500)):
                self.safe_create(
                    BlogView,
                    post=post,
                    user=random.choice(users) if random.random() < 0.7 else None,
                    ip_address=fake.ipv4(),
                    user_agent=fake.user_agent(),
                    referrer=fake.url() if random.random() < 0.5 else "",
                )

        # Create blog series
        for _ in range(10):
            series = self.safe_create(
                BlogSeries,
                title=fake.catch_phrase(),
                slug=fake.unique.slug(),
                description=fake.text(max_nb_chars=500),
                author=random.choice(users),
                is_active=True,
            )

            if series:
                # Add posts to series
                series_posts = random.sample(blog_posts, random.randint(2, 5))
                for i, post in enumerate(series_posts):
                    self.safe_create(
                        BlogSeriesPost,
                        series=series,
                        post=post,
                        order=i + 1,
                    )

        # Create blog badges
        badge_data = [
            {
                "name": "First Post",
                "description": "Published your first blog post",
                "points": 1,
            },
            {
                "name": "Popular Writer",
                "description": "Got 1000+ views on a post",
                "points": 50,
            },
            {
                "name": "Consistent Blogger",
                "description": "Published 10 posts",
                "points": 25,
            },
            {
                "name": "Community Favorite",
                "description": "Got 100+ likes",
                "points": 30,
            },
        ]

        blog_badges = []
        for badge_info in badge_data:
            badge = self.safe_create(BlogBadge, **badge_info)
            if badge:
                blog_badges.append(badge)

        # Award badges to users
        for user in users[:20]:
            for _ in range(random.randint(1, 3)):
                badge = random.choice(blog_badges)
                self.safe_create(
                    UserBlogBadge,
                    user=user,
                    badge=badge,
                    progress=random.randint(badge.points, badge.points + 10),
                )

        self.stdout.write("Blog data created successfully")

    def create_event_data(self):
        """Create comprehensive event data."""
        self.stdout.write("Creating event data...")

        users = list(User.objects.all())

        # Create event categories
        event_category_data = [
            {
                "name": "Technology",
                "description": "Tech conferences and workshops",
                "icon": "fa-laptop",
                "color": "#3b82f6",
            },
            {
                "name": "Business",
                "description": "Business and entrepreneurship events",
                "icon": "fa-briefcase",
                "color": "#10b981",
            },
            {
                "name": "Education",
                "description": "Educational seminars and courses",
                "icon": "fa-graduation-cap",
                "color": "#8b5cf6",
            },
            {
                "name": "Health",
                "description": "Health and wellness events",
                "icon": "fa-heart",
                "color": "#ef4444",
            },
            {
                "name": "Arts",
                "description": "Arts and culture events",
                "icon": "fa-palette",
                "color": "#f59e0b",
            },
        ]

        event_categories = []
        for cat_data in event_category_data:
            category = self.safe_create(
                EventCategory,
                name=cat_data["name"],
                slug=cat_data["name"].lower(),
                description=cat_data["description"],
                icon=cat_data["icon"],
                color=cat_data["color"],
                is_active=True,
            )
            if category:
                event_categories.append(category)

        # Create event tags
        event_tag_names = [
            "Conference",
            "Workshop",
            "Networking",
            "Online",
            "Free",
            "Beginner",
            "Advanced",
            "Certification",
            "Hands-on",
            "Panel",
        ]

        event_tags = []
        for tag_name in event_tag_names:
            tag = self.safe_create(
                EventTag,
                name=tag_name,
                slug=tag_name.lower(),
                description=f"Events related to {tag_name}",
                color=fake.hex_color(),
            )
            if tag:
                event_tags.append(tag)

        # Create events
        events = []
        for _ in range(50):
            start_date = fake.date_time_between(
                start_date="-30d", end_date="+6M", tzinfo=dt_timezone.utc
            )
            end_date = start_date + timedelta(hours=random.randint(2, 72))

            event = self.safe_create(
                Event,
                name=fake.catch_phrase(),
                slug=fake.unique.slug(),
                description=fake.text(max_nb_chars=2000),
                raw_description=fake.text(max_nb_chars=300),
                organizer=random.choice(users),
                type=random.choice(Event.EventType.choices)[0],
                status=random.choice(Event.EventStatus.choices)[0],
                visibility=random.choice(Event.Visibility.choices)[0],
                start_date=start_date,
                end_date=end_date,
                timezone="UTC",
                location=fake.address(),
                venue_name=fake.company(),
                virtual_link=fake.url() if random.random() < 0.6 else "",
                capacity=random.randint(20, 500) if random.random() < 0.8 else None,
                currency="USD",
                # registration_start_date=fake.date_time_between(
                #     start_date="-60d", end_date=start_date, tzinfo=dt_timezone.utc
                # ),
                # registration_end_date=start_date - timedelta(days=1),
                # requires_approval=random.choice([True, False]),
                is_featured=random.choice([True, False]),
                allow_comments=random.choice([True, False]),
            )
            if event:
                events.append(event)

        # Create event category and tag relations
        for event in events:
            if event_categories and random.random() < 0.9:
                category = random.choice(event_categories)
                self.safe_create(
                    EventCategoryRelation,
                    event=event,
                    category=category,
                    is_primary=True,
                )

            if event_tags:
                selected_tags = random.sample(event_tags, random.randint(1, 4))
                for tag in selected_tags:
                    self.safe_create(
                        EventTagRelation,
                        event=event,
                        tag=tag,
                    )

        # Create sessions
        sessions = []
        for event in events:
            for _ in range(random.randint(1, 8)):
                session_start = event.start_date + timedelta(
                    hours=random.randint(0, 24)
                )
                session_end = session_start + timedelta(hours=random.randint(1, 4))

                session = self.safe_create(
                    Session,
                    event=event,
                    title=fake.catch_phrase(),
                    description=fake.text(max_nb_chars=1000),
                    speaker=random.choice(users),
                    session_type=random.choice(Session.SessionType.choices)[0],
                    start_time=session_start,
                    end_time=session_end,
                    location=fake.word(),
                    capacity=random.randint(10, 100) if random.random() < 0.7 else None,
                    is_featured=random.choice([True, False]),
                )
                if session:
                    sessions.append(session)

        # Create participants
        for event in events:
            num_participants = random.randint(
                5, min(50, event.participants.count() or 50)
            )
            event_users = random.sample(users, num_participants)

            for user in event_users:
                self.safe_create(
                    Participant,
                    event=event,
                    user=user,
                    role=random.choice(Participant.Role.choices)[0],
                    registration_status=random.choice(
                        Participant.RegistrationStatus.choices
                    )[0],
                    attendance_status=random.choice(
                        Participant.AttendanceStatus.choices
                    )[0],
                    registration_data={
                        "company": fake.company(),
                        "dietary_restrictions": fake.word(),
                    },
                    check_in_time=timezone.now() if random.random() < 0.6 else None,
                )

        # Create exhibitors
        for event in events[:20]:  # Only for some events
            for _ in range(random.randint(1, 5)):
                self.safe_create(
                    Exhibitor,
                    event=event,
                    company_name=fake.company(),
                    description=fake.text(max_nb_chars=800),
                    contact_person=random.choice(users),
                    sponsorship_tier=random.choice(Exhibitor.SponsorshipTier.choices)[
                        0
                    ],
                    booth_number=f"B{random.randint(1, 100)}",
                    website=fake.url(),
                    is_sponsor=random.choice([True, False]),
                )

        # Create event badges
        badge_data = [
            {
                "name": "Early Bird",
                "description": "Registered early",
                "color": "#10b981",
            },
            {"name": "Speaker", "description": "Event speaker", "color": "#3b82f6"},
            {"name": "Sponsor", "description": "Event sponsor", "color": "#f59e0b"},
            {"name": "Attendee", "description": "Event attendee", "color": "#6b7280"},
        ]

        event_badges = []
        for badge_info in badge_data:
            badge = self.safe_create(EventBadge, **badge_info)
            if badge:
                event_badges.append(badge)

        # Award badges to participants
        participants = list(Participant.objects.all())
        for participant in participants[:100]:
            badge = random.choice(event_badges)
            self.safe_create(
                ParticipantBadge,
                participant=participant,
                badge=badge,
                points_earned=random.randint(1, 50),
            )

        # Create event analytics
        for event in events:
            self.safe_create(
                EventAnalytics,
                event=event,
                total_registrations=random.randint(10, 200),
                confirmed_attendees=random.randint(5, 150),
                no_shows=random.randint(0, 20),
                total_views=random.randint(100, 5000),
                unique_views=random.randint(50, 2000),
                social_shares=random.randint(0, 100),
                rating_average=Decimal(random.uniform(3.0, 5.0)),
                rating_count=random.randint(0, 50),
            )

        self.stdout.write("Event data created successfully")

    def create_chat_data(self):
        """Create comprehensive chat data."""
        self.stdout.write("Creating chat data...")

        users = list(User.objects.all())

        # Create chat themes
        theme_data = [
            {
                "name": "Default",
                "title": "Default Theme",
                "accent_color": "#3b82f6",
                "background_color": "#ffffff",
            },
            {
                "name": "Dark",
                "title": "Dark Theme",
                "accent_color": "#8b5cf6",
                "background_color": "#1f2937",
            },
            {
                "name": "Blue",
                "title": "Blue Theme",
                "accent_color": "#2563eb",
                "background_color": "#eff6ff",
            },
        ]

        for theme_info in theme_data:
            self.safe_create(ChatTheme, **theme_info)

        # Create sticker sets
        sticker_sets = []
        for _ in range(5):
            sticker_set = self.safe_create(
                ChatStickerSet,
                name=fake.word(),
                title=fake.catch_phrase(),
                sticker_type=random.choice(ChatStickerSet.StickerType.choices)[0],
                creator=random.choice(users),
                is_official=random.choice([True, False]),
            )
            if sticker_set:
                sticker_sets.append(sticker_set)

        # Create stickers
        for sticker_set in sticker_sets:
            for _ in range(random.randint(5, 20)):
                self.safe_create(
                    ChatSticker,
                    sticker_set=sticker_set,
                    emoji=random.choice(
                        ["😀", "😃", "😄", "😁", "😆", "😅", "😂", "🤣"]
                    ),
                    width=random.randint(100, 512),
                    height=random.randint(100, 512),
                )

        # Create chats
        chats = []
        for _ in range(30):
            chat = self.safe_create(
                Chat,
                title=fake.company() if random.random() < 0.7 else None,
                description=fake.text(max_nb_chars=500)
                if random.random() < 0.5
                else "",
                chat_type=random.choice(Chat.ChatType.choices)[0],
                status=random.choice(Chat.ChatStatus.choices)[0],
                creator=random.choice(users),
                is_public=random.choice([True, False]),
                max_participants=random.randint(2, 200)
                if random.random() < 0.8
                else None,
                slow_mode_delay=random.randint(0, 300) if random.random() < 0.3 else 0,
                auto_delete_timer=random.randint(3600, 86400)
                if random.random() < 0.2
                else None,
            )
            if chat:
                chats.append(chat)

        # Create chat participants
        for chat in chats:
            num_participants = random.randint(2, min(20, chat.max_participants or 20))
            chat_users = random.sample(users, num_participants)

            for i, user in enumerate(chat_users):
                role = (
                    ChatParticipant.ParticipantRole.OWNER
                    if i == 0
                    else random.choice(
                        [
                            ChatParticipant.ParticipantRole.ADMIN,
                            ChatParticipant.ParticipantRole.MEMBER,
                            ChatParticipant.ParticipantRole.MEMBER,  # More likely to be member
                        ]
                    )[0]
                )

                self.safe_create(
                    ChatParticipant,
                    chat=chat,
                    user=user,
                    role=role,
                    status=random.choice(ChatParticipant.ParticipantStatus.choices)[0],
                    can_send_messages=True,
                    can_send_media=True,
                    can_add_users=role
                    in [
                        ChatParticipant.ParticipantRole.OWNER,
                        ChatParticipant.ParticipantRole.ADMIN,
                    ],
                )

        # Create chat messages
        for chat in chats:
            participants = list(chat.participants.all())
            for _ in range(random.randint(10, 100)):
                sender = random.choice(participants)
                message = self.safe_create(
                    ChatMessage,
                    chat=chat,
                    sender=sender.user,
                    message_type=random.choice(ChatMessage.MessageType.choices)[0],
                    content=fake.text(max_nb_chars=500),
                    status=random.choice(ChatMessage.MessageStatus.choices)[0],
                    is_edited=random.choice([True, False]),
                )

                # Create replies
                if message and random.random() < 0.2:
                    self.safe_create(
                        ChatMessage,
                        chat=chat,
                        sender=random.choice(participants).user,
                        reply_to=message,
                        message_type="text",
                        content=fake.sentence(),
                        status="sent",
                    )

        self.stdout.write("Chat data created successfully")

    def create_payment_data(self):
        """Create payment data."""
        self.stdout.write("Creating payment data...")

        users = list(User.objects.all())
        gateways = list(PaymentGatewayConfig.objects.all())

        if not gateways:
            self.stdout.write("No payment gateways found, skipping payment data")
            return

        # Create payments
        payments = []
        for _ in range(200):
            payment = self.safe_create(
                Payment,
                user=random.choice(users),
                gateway=random.choice(gateways),
                amount=Decimal(random.uniform(10.0, 1000.0)).quantize(Decimal("0.01")),
                currency=random.choice(Payment.Currency.choices)[0],
                status=random.choice(Payment.Status.choices)[0],
                metadata={"order_id": str(uuid.uuid4()), "product": fake.word()},
            )
            if payment:
                payments.append(payment)

        # Create transactions
        for payment in payments:
            if random.random() < 0.8:  # 80% of payments have transactions
                self.safe_create(
                    Transaction,
                    payment=payment,
                    status=random.choice(Transaction.Status.choices)[0],
                    gateway_transaction_id=str(uuid.uuid4()),
                    gateway_response={
                        "status": "success",
                        "reference": str(uuid.uuid4()),
                    },
                )

        # Create refunds
        successful_payments = [p for p in payments if p.status == "SUCCESS"]
        for payment in random.sample(
            successful_payments, min(20, len(successful_payments))
        ):
            self.safe_create(
                Refund,
                payment=payment,
                user=payment.user,
                amount=payment.amount,
                reason=fake.sentence(),
                status="PENDING",
            )

        self.stdout.write("Payment data created successfully")

    def create_notification_data(self):
        """Create notification data."""
        self.stdout.write("Creating notification data...")

        users = list(User.objects.all())

        # Create notification templates
        template_data = [
            {
                "name": "welcome",
                "subject": "Welcome to our platform!",
                "message": "Hello {username}, welcome to our platform!",
            },
            {
                "name": "password_reset",
                "subject": "Password Reset Request",
                "message": "Click here to reset your password: {reset_link}",
            },
            {
                "name": "event_reminder",
                "subject": "Event Reminder",
                "message": "Don't forget about the event: {event_title}",
            },
            {
                "name": "new_message",
                "subject": "New Message",
                "message": "You have a new message from {sender}",
            },
        ]

        templates = []
        for template_info in template_data:
            template = self.safe_create(NotificationTemplate, **template_info)
            if template:
                templates.append(template)

        # Create notification batches
        for _ in range(10):
            self.safe_create(
                NotificationBatch,
                description=fake.sentence(),
                recipient_count=random.randint(10, 100),
                sent_count=random.randint(5, 95),
                failed_count=random.randint(0, 10),
            )

        # Create notifications
        for user in users:
            for _ in range(random.randint(5, 30)):
                template = (
                    random.choice(templates)
                    if templates and random.random() < 0.5
                    else None
                )
                self.safe_create(
                    Notification,
                    user=user,
                    template=template,
                    title=fake.sentence(),
                    message=fake.text(max_nb_chars=500),
                    priority=random.choice(Notification.Priority.choices)[0],
                    channels=[random.choice(Notification.Channel.choices)[0]],
                    status=random.choice(Notification.Status.choices)[0],
                    is_read=random.choice([True, False]),
                    metadata={"action_url": fake.url(), "category": fake.word()},
                )

        self.stdout.write("Notification data created successfully")

    def create_feedback_data(self):
        """Create feedback data."""
        self.stdout.write("Creating feedback data...")

        users = list(User.objects.all())

        for _ in range(150):
            self.safe_create(
                Feedback,
                user=random.choice(users) if random.random() < 0.8 else None,
                feedback_type=random.choice(Feedback.FeedbackType.choices)[0],
                status=random.choice(Feedback.Status.choices)[0],
                title=fake.catch_phrase(),
                description=fake.text(max_nb_chars=1000),
                metadata={
                    "browser": fake.user_agent(),
                    "page_url": fake.url(),
                    "ip_address": fake.ipv4(),
                },
            )

        self.stdout.write("Feedback data created successfully")

    def create_audit_data(self):
        """Create audit log data."""
        self.stdout.write("Creating audit data...")

        users = list(User.objects.all())

        for _ in range(500):
            self.safe_create(
                AuditLog,
                user=random.choice(users) if random.random() < 0.9 else None,
                action_type=random.choice(AuditLog.ActionType.choices)[0],
                status=random.choice(AuditLog.Status.choices)[0],
                priority=random.choice(AuditLog.Priority.choices)[0],
                ip_address=fake.ipv4(),
                user_agent=fake.user_agent(),
                object_repr=fake.sentence(),
                changes={
                    "before": {"status": fake.word()},
                    "after": {"status": fake.word()},
                }
                if random.random() < 0.6
                else {},
                metadata={
                    "request_method": random.choice(["GET", "POST", "PUT", "DELETE"]),
                    "request_url": fake.url(),
                    "response_status": random.choice([200, 201, 400, 404, 500]),
                },
                error_message=fake.sentence() if random.random() < 0.2 else "",
            )

        self.stdout.write("Audit data created successfully")
