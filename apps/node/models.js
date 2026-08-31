const { Sequelize, DataTypes, Model } = require('sequelize')

const sequelize = new Sequelize(
  process.env.DB_NAME || 'blogbench',
  process.env.DB_USER || 'bench',
  process.env.DB_PASSWORD || 'bench',
  {
    host: process.env.DB_HOST || 'mysql',
    dialect: 'mysql',
    logging: false,
    timezone: '+00:00',
    define: { timestamps: false, freezeTableName: true },
    pool: { max: Number(process.env.DB_POOL || 5), min: 0, idle: 10000 },
  }
)

class User extends Model {}
User.init(
  {
    id: { type: DataTypes.BIGINT.UNSIGNED, primaryKey: true, autoIncrement: true },
    name: DataTypes.STRING,
    email: DataTypes.STRING,
    bio: DataTypes.TEXT,
    created_at: DataTypes.DATE,
    updated_at: DataTypes.DATE,
  },
  { sequelize, tableName: 'users' }
)

class Tag extends Model {}
Tag.init(
  {
    id: { type: DataTypes.BIGINT.UNSIGNED, primaryKey: true, autoIncrement: true },
    name: DataTypes.STRING,
    slug: DataTypes.STRING,
  },
  { sequelize, tableName: 'tags' }
)

class Post extends Model {}
Post.init(
  {
    id: { type: DataTypes.BIGINT.UNSIGNED, primaryKey: true, autoIncrement: true },
    user_id: DataTypes.BIGINT.UNSIGNED,
    title: DataTypes.STRING,
    slug: DataTypes.STRING,
    body: DataTypes.TEXT,
    status: DataTypes.STRING,
    view_count: DataTypes.INTEGER,
    comments_count: DataTypes.INTEGER,
    published_at: DataTypes.DATE,
    created_at: DataTypes.DATE,
    updated_at: DataTypes.DATE,
  },
  { sequelize, tableName: 'posts' }
)

class Comment extends Model {}
Comment.init(
  {
    id: { type: DataTypes.BIGINT.UNSIGNED, primaryKey: true, autoIncrement: true },
    post_id: DataTypes.BIGINT.UNSIGNED,
    user_id: DataTypes.BIGINT.UNSIGNED,
    body: {
      type: DataTypes.TEXT,
      validate: { notEmpty: true, len: [1, 2000] },
    },
    created_at: DataTypes.DATE,
    updated_at: DataTypes.DATE,
  },
  {
    sequelize,
    tableName: 'comments',
    hooks: {
      beforeValidate(c) {
        if (typeof c.body === 'string') c.body = c.body.trim().split(/\s+/).join(' ')
      },
    },
  }
)

class PostTag extends Model {}
PostTag.init(
  {
    id: { type: DataTypes.BIGINT.UNSIGNED, primaryKey: true, autoIncrement: true },
    post_id: DataTypes.BIGINT.UNSIGNED,
    tag_id: DataTypes.BIGINT.UNSIGNED,
  },
  { sequelize, tableName: 'post_tags' }
)

Post.belongsTo(User, { foreignKey: 'user_id', as: 'author' })
Comment.belongsTo(User, { foreignKey: 'user_id', as: 'author' })
PostTag.belongsTo(Tag, { foreignKey: 'tag_id', as: 'tag' })

module.exports = { sequelize, User, Tag, Post, Comment, PostTag }
